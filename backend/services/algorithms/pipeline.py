"""
The multi-evidence change-detection pipeline.

    Before image + After image
      -> Registration
      -> Radiometric normalization
      -> Cloud/quality masking
      -> EO feature extraction
      -> Deep feature difference  ─┐
      -> Spectral differences      ├─> Evidence fusion
      -> Spatial/context consistency ┘
      -> False-alarm suppression
      -> Change mask
      -> Change type
      -> Confidence

Deliberately array-in / array-out: it takes two rasters and returns a
`ChangeAnalysis`, with no database, rasterio or model-loading dependency. The
EO feature extractor is injected by the caller (services.change_detection
supplies the Prithvi-EO service), which keeps the science unit-testable
against plain NumPy fixtures and lets the deep layer degrade gracefully to a
spectral + spatial detection when no extractor is available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from services.algorithms.change_classifier import ChangeRegion, classify_change_regions
from services.algorithms.evidence import (
    DEFAULT_CONTEXT_RADIUS,
    EvidenceLayer,
    deep_evidence,
    spatial_evidence,
    spectral_evidence,
)
from services.algorithms.fusion import FusionResult, fuse_evidence
from services.algorithms.imageops import resize_to
from services.algorithms.masking import QualityMask, compute_quality_mask, joint_valid_mask
from services.algorithms.normalization import NormalizationResult, normalize_relative_radiometry
from services.algorithms.registration import RegistrationResult, apply_transform, register_image_pair
from services.algorithms.spectral import SpectralIndices, compute_spectral_indices
from services.algorithms.suppression import SuppressionMaps, suppress_false_alarms

PIPELINE_VERSION = "multi-evidence-1.0"

DEFAULT_WEIGHTS = {"deep_feature": 0.45, "spectral": 0.35, "spatial_context": 0.20}


@dataclass
class Observation:
    """One side of the bi-temporal pair, as the pipeline needs it."""

    raster: np.ndarray                              # (H, W, C) reflectance in [0, 1]
    band_map: Optional[Dict[str, int]] = None
    scl: Optional[np.ndarray] = None                # raw scene-classification codes
    ingest_mask: Optional[np.ndarray] = None        # ingest-time quality mask
    indices: Optional[SpectralIndices] = None       # precomputed spectral indices
    label: str = ""


@dataclass
class PipelineStage:
    """An auditable record of one pipeline stage."""

    name: str
    status: str                      # "ok" | "degraded" | "skipped"
    detail: str
    metrics: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"stage": self.name, "status": self.status, "detail": self.detail, "metrics": self.metrics}


@dataclass
class ChangeAnalysis:
    """Everything the pipeline derived about one before/after pair."""

    change_probability: np.ndarray
    change_mask: np.ndarray
    registration: RegistrationResult
    normalization: NormalizationResult
    before_mask: QualityMask
    after_mask: QualityMask
    joint_valid: np.ndarray
    layers: List[EvidenceLayer]
    fusion: FusionResult
    suppression: SuppressionMaps
    before_indices: SpectralIndices
    after_indices: SpectralIndices
    index_deltas: Dict[str, np.ndarray]
    regions: List[ChangeRegion]
    aligned_after: np.ndarray
    normalized_after: np.ndarray
    stages: List[PipelineStage] = field(default_factory=list)
    # Mean fused probability inside the detected change (not a tile average).
    raw_change_score: float = 0.0
    changed_fraction: float = 0.0
    clear_fraction: float = 0.0
    # Weighted share of evidence layers agreeing inside the detected change.
    evidence_agreement: float = 0.0
    radiometric_shift: float = 0.0
    deep_available: bool = False
    deep_is_placeholder: bool = True
    feature_model: str = "none"

    @property
    def dominant_change_type(self) -> str:
        areas: Dict[str, int] = {}
        for region in self.regions:
            areas[region.change_type] = areas.get(region.change_type, 0) + region.area_pixels
        return max(areas, key=areas.get) if areas else "no_significant_change"

    @property
    def dominant_dynamics(self) -> str:
        areas: Dict[str, int] = {}
        for region in self.regions:
            areas[region.dynamics] = areas.get(region.dynamics, 0) + region.area_pixels
        return max(areas, key=areas.get) if areas else "stable"

    def stage_dicts(self) -> List[Dict[str, Any]]:
        return [stage.as_dict() for stage in self.stages]

    def layer_summaries(self, threshold: float = 0.5) -> List[Dict[str, Any]]:
        return [layer.summary(self.joint_valid, threshold) for layer in self.layers]


def _as_hwc(raster: np.ndarray) -> np.ndarray:
    arr = np.asarray(raster, dtype=np.float32)
    if arr.ndim == 2:
        return arr[..., None]
    if arr.ndim == 3 and arr.shape[0] <= 16 and arr.shape[0] < arr.shape[1] and arr.shape[0] < arr.shape[2]:
        return np.transpose(arr, (1, 2, 0))
    return arr


def _warp_like(
    plane: Optional[np.ndarray],
    registration: RegistrationResult,
    height: int,
    width: int,
) -> Optional[np.ndarray]:
    """Carry an ancillary plane through the same warp applied to the imagery."""
    if plane is None:
        return None
    warped = apply_transform(np.asarray(plane), registration.transform_matrix, height, width)
    return warped if np.asarray(warped).shape[:2] == (height, width) else None


def _region_evidence(
    regions: List[ChangeRegion],
    mask: np.ndarray,
    layers: List[EvidenceLayer],
    agreement: np.ndarray,
) -> Dict[int, Dict[str, float]]:
    """Mean evidence-layer response inside each detected region."""
    if not regions:
        return {}
    from services.algorithms.imageops import connected_labels

    labels, _ = connected_labels(mask.astype(np.uint8))
    per_region: Dict[int, Dict[str, float]] = {}
    for region in regions:
        selection = labels == region.region_id
        if not selection.any():
            continue
        entry = {
            layer.name: round(float(layer.probability[selection].mean()), 4) for layer in layers
        }
        entry["agreement"] = round(float(agreement[selection].mean()), 4)
        per_region[region.region_id] = entry
    return per_region


def analyze_change_pair(
    before: Observation,
    after: Observation,
    feature_extractor: Optional[Callable[[np.ndarray, Optional[Dict[str, int]]], Tuple[np.ndarray, str, bool]]] = None,
    threshold: float = 0.5,
    weights: Optional[Dict[str, float]] = None,
    context_radius: int = DEFAULT_CONTEXT_RADIUS,
    min_region_pixels: int = 8,
    cloud_dilation: int = 2,
) -> ChangeAnalysis:
    """
    Run the full multi-evidence change pipeline on one before/after pair.

    Args:
        before / after: the two observations, already loaded as [0, 1] rasters.
        feature_extractor: callable `(raster_hwc, band_map) -> (feature_grid,
            model_name, is_placeholder)`. When omitted the deep layer is
            skipped and fusion proceeds on spectral + spatial evidence alone.
        threshold: probability above which a pixel counts as changed.
        weights: per-layer prior weights; defaults to DEFAULT_WEIGHTS.
        context_radius: window radius for spatial/context consistency.
        min_region_pixels: smallest region kept by suppression and typing.
        cloud_dilation: radius by which cloud/shadow masks are grown.
    """
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    stages: List[PipelineStage] = []

    before_raster = _as_hwc(before.raster)
    after_raster = _as_hwc(after.raster)
    height, width = before_raster.shape[:2]

    # --- 1. Registration ---------------------------------------------------
    registration = register_image_pair(before_raster, after_raster)
    aligned_after = _as_hwc(registration.aligned_after)
    if aligned_after.shape[:2] != (height, width):
        aligned_after = resize_to(aligned_after, height, width)
    stages.append(PipelineStage(
        name="registration",
        status="ok" if registration.is_aligned else "degraded",
        detail=(
            f"Co-registered the after image onto the before frame "
            f"(dx={registration.dx:.2f}px, dy={registration.dy:.2f}px, "
            f"{registration.inliers} inliers); correlation "
            f"{registration.correlation_before:.3f} → {registration.correlation_after:.3f}."
        ),
        metrics={
            "is_aligned": bool(registration.is_aligned),
            "dx": round(float(registration.dx), 3),
            "dy": round(float(registration.dy), 3),
            "residual_shift_px": round(registration.residual_shift_px, 3),
            "inliers": int(registration.inliers),
            "correlation_before": round(float(registration.correlation_before), 4),
            "correlation_after": round(float(registration.correlation_after), 4),
        },
    ))

    # --- 2. Cloud / quality masking (needed before normalization fits) -----
    before_mask = compute_quality_mask(
        before_raster, before.band_map, before.scl, before.ingest_mask, cloud_dilation
    )
    # The after image was warped into the before frame, so its ancillary
    # planes must ride along or they will mask the wrong pixels.
    after_scl = _warp_like(after.scl, registration, height, width)
    after_ingest = _warp_like(after.ingest_mask, registration, height, width)
    after_mask = compute_quality_mask(
        aligned_after, after.band_map, after_scl, after_ingest, cloud_dilation
    )
    joint_valid = joint_valid_mask(before_mask, after_mask, registration.footprint)
    clear_fraction = float(joint_valid.mean())
    stages.append(PipelineStage(
        name="quality_masking",
        status="ok" if clear_fraction >= 0.5 else "degraded",
        detail=(
            f"{clear_fraction * 100:.1f}% of the tile is usable in both dates "
            f"(before {before_mask.method}: {before_mask.clear_fraction * 100:.1f}% clear, "
            f"after {after_mask.method}: {after_mask.clear_fraction * 100:.1f}% clear)."
        ),
        metrics={
            "joint_clear_fraction": round(clear_fraction, 4),
            "before": before_mask.summary(),
            "after": after_mask.summary(),
        },
    ))
    if not joint_valid.any():
        # Nothing comparable — fall back to the full frame so the pipeline can
        # still report, with the degraded status recorded above.
        joint_valid = np.ones((height, width), dtype=bool)

    # --- 3. Radiometric normalization on invariant, clear pixels -----------
    normalization = normalize_relative_radiometry(aligned_after, before_raster, joint_valid)
    normalized_after = _as_hwc(normalization.array)
    stages.append(PipelineStage(
        name="radiometric_normalization",
        status="ok" if normalization.method != "identity" else "skipped",
        detail=normalization.detail,
        metrics=normalization.summary(),
    ))

    # --- 4. Spectral indices ------------------------------------------------
    before_indices = before.indices or compute_spectral_indices(before_raster, before.band_map)
    after_indices = compute_spectral_indices(normalized_after, after.band_map)

    # --- 5/6. EO features + deep feature difference ------------------------
    layers: List[EvidenceLayer] = []
    deep_available = False
    deep_is_placeholder = True
    feature_model = "none"
    if feature_extractor is not None:
        try:
            before_features, model_name, before_placeholder = feature_extractor(before_raster, before.band_map)
            after_features, _, after_placeholder = feature_extractor(normalized_after, after.band_map)
            deep_is_placeholder = bool(before_placeholder or after_placeholder)
            feature_model = model_name
            layers.append(deep_evidence(
                before_features,
                after_features,
                (height, width),
                joint_valid,
                is_placeholder=deep_is_placeholder,
                model_name=model_name,
                weight=weights["deep_feature"],
            ))
            deep_available = True
            stages.append(PipelineStage(
                name="deep_feature_difference",
                status="degraded" if deep_is_placeholder else "ok",
                detail=layers[-1].detail,
                metrics=layers[-1].stats,
            ))
        except Exception as exc:  # feature extraction must never sink the run
            stages.append(PipelineStage(
                name="deep_feature_difference",
                status="skipped",
                detail=f"EO feature extraction unavailable ({exc}); fused on spectral + spatial evidence.",
                metrics={},
            ))
    else:
        stages.append(PipelineStage(
            name="deep_feature_difference",
            status="skipped",
            detail="No EO feature extractor supplied; fused on spectral + spatial evidence.",
            metrics={},
        ))

    # --- 7. Spectral differences -------------------------------------------
    spectral_layer, index_deltas = spectral_evidence(
        before_raster,
        normalized_after,
        before_indices,
        after_indices,
        before.band_map,
        after.band_map,
        joint_valid,
        weight=weights["spectral"],
    )
    layers.append(spectral_layer)
    stages.append(PipelineStage(
        name="spectral_difference",
        status="ok" if spectral_layer.reliability >= 1.0 else "degraded",
        detail=spectral_layer.detail,
        metrics=spectral_layer.stats,
    ))

    # --- 8. Spatial / context consistency ----------------------------------
    spatial_layer = spatial_evidence(
        before_raster,
        normalized_after,
        joint_valid,
        radius=context_radius,
        weight=weights["spatial_context"],
    )
    layers.append(spatial_layer)
    stages.append(PipelineStage(
        name="spatial_context_consistency",
        status="ok",
        detail=spatial_layer.detail,
        metrics=spatial_layer.stats,
    ))

    # --- 9. Evidence fusion -------------------------------------------------
    fusion = fuse_evidence(layers, joint_valid, layer_threshold=threshold)
    stages.append(PipelineStage(
        name="evidence_fusion",
        status="ok" if len(layers) >= 2 else "degraded",
        detail=fusion.detail,
        metrics=fusion.summary(joint_valid),
    ))

    # --- 10. False-alarm suppression ---------------------------------------
    suppression = suppress_false_alarms(
        fusion.probability,
        joint_valid,
        before_raster,
        threshold=threshold,
        residual_shift_px=registration.residual_shift_px,
        registration_aligned=registration.is_aligned,
        context_radius=context_radius,
        min_region_pixels=min_region_pixels,
    )
    stages.append(PipelineStage(
        name="false_alarm_suppression",
        status="ok",
        detail=(
            f"{suppression.removed_fraction * 100:.1f}% of candidate change pixels removed across "
            f"{len(suppression.stages)} suppressors; {suppression.changed_pixels} pixel(s) retained."
        ),
        metrics=suppression.summary(),
    ))

    # --- 11. Change mask ----------------------------------------------------
    change_mask = suppression.mask
    stages.append(PipelineStage(
        name="change_mask",
        status="ok" if suppression.changed_pixels > 0 else "degraded",
        detail=(
            f"Binary change mask covers {suppression.changed_fraction * 100:.2f}% of the tile "
            f"at a fused probability threshold of {threshold:.2f}."
        ),
        metrics={
            "threshold": threshold,
            "changed_pixels": int(suppression.changed_pixels),
            "changed_fraction": round(float(suppression.changed_fraction), 5),
        },
    ))

    # --- 12. Change typing --------------------------------------------------
    regions = classify_change_regions(
        change_mask=change_mask,
        before_indices=before_indices,
        after_indices=after_indices,
        min_region_size=min_region_pixels,
    )
    region_evidence = _region_evidence(regions, change_mask, layers, fusion.agreement)
    for region in regions:
        evidence = region_evidence.get(region.region_id)
        if not evidence:
            continue
        # Region confidence is the classifier's spectral confidence tempered by
        # how much independent evidence actually supports that region.
        region.confidence = round(
            float(np.clip(region.confidence * (0.7 + 0.3 * evidence.get("agreement", 0.0)), 0.0, 1.0)), 3
        )
    stages.append(PipelineStage(
        name="change_typing",
        status="ok" if regions else "degraded",
        detail=(
            f"{len(regions)} region(s) classified into "
            f"{sorted({region.change_type for region in regions}) or ['none']}."
        ),
        metrics={"region_count": len(regions), "region_evidence": region_evidence},
    ))

    # Scene-level figures are taken over the detected change, not the whole
    # tile. A tile-wide average of a correctly localised 2% detection is ~0.05
    # and reads as "nothing happened"; what an analyst needs is how strong the
    # evidence is *where* change was found, alongside how much area it covers.
    detected = change_mask.astype(bool)
    if detected.any():
        raw_change_score = float(suppression.probability[detected].mean())
        evidence_agreement = float(fusion.agreement[detected].mean())
    elif joint_valid.any():
        raw_change_score = float(np.percentile(suppression.probability[joint_valid], 99))
        evidence_agreement = float(fusion.agreement[joint_valid].mean())
    else:
        raw_change_score = 0.0
        evidence_agreement = 0.0

    return ChangeAnalysis(
        change_probability=suppression.probability,
        change_mask=change_mask,
        registration=registration,
        normalization=normalization,
        before_mask=before_mask,
        after_mask=after_mask,
        joint_valid=joint_valid,
        layers=layers,
        fusion=fusion,
        suppression=suppression,
        before_indices=before_indices,
        after_indices=after_indices,
        index_deltas=index_deltas,
        regions=regions,
        aligned_after=aligned_after,
        normalized_after=normalized_after,
        stages=stages,
        raw_change_score=raw_change_score,
        changed_fraction=float(suppression.changed_fraction),
        clear_fraction=clear_fraction,
        evidence_agreement=evidence_agreement,
        radiometric_shift=float(normalization.shift_before),
        deep_available=deep_available,
        deep_is_placeholder=deep_is_placeholder,
        feature_model=feature_model,
    )
