"""
Independent change-evidence layers — stages 5-8 of the change pipeline.

A single embedding difference is a weak detector: it fires on illumination
drift, on sensor gain differences, on registration residual, and on genuine
ground change alike, and it cannot say which. This module computes three
*independently derived* pieces of evidence for the same pixel:

  1. Deep EO feature divergence   — semantic change in Prithvi-EO patch tokens.
  2. Spectral divergence          — change vector analysis + NDVI/NDWI/NDBI shift.
  3. Spatial/context consistency  — local structural dissimilarity and texture
                                    energy change (illumination invariant).

Each layer reports a calibrated probability map, a reliability weight that
reflects how trustworthy that layer is for *this* observation pair (e.g. the
spectral layer is downweighted when only RGB proxies are available), and the
statistics behind it. services.algorithms.fusion combines them.

All probability maps are calibrated the same way — see `robust_probability` —
so the fused number keeps a consistent meaning across layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

from services.algorithms.imageops import (
    EPS,
    box_mean,
    gradient_magnitude,
    local_structure_stats,
    resize_to,
    robust_center_scale,
    to_gray,
)
from services.algorithms.spectral import SpectralIndices

# Relative-anomaly shaping: how many robust sigmas above the scene median a
# pixel must sit before it is considered anomalous, and how sharp that gate is.
ANOMALY_Z_MIDPOINT = 2.0
ANOMALY_Z_SOFTNESS = 0.8

# Calibration per metric: (floor, scale_min, scale_max).
#
# A difference at or below `floor` is no evidence at all — that absolute gate is
# what keeps an unchanged pair at zero, which a min-max or pure z-score
# normalisation cannot do. Above it, the saturation span adapts to the spread
# actually observed in the scene, clamped to [scale_min, scale_max]: the same
# cosine distance means different things in a 768-dimension Prithvi embedding
# and in a 7-dimension statistical stand-in, so a single hard-coded span would
# be right for one feature space and wrong for the other. The clamp stops the
# span from collapsing onto sensor noise or widening past a real signal.
DEEP_COSINE_CAL = (0.010, 0.040, 0.30)
DEEP_MAGNITUDE_CAL = (0.030, 0.100, 0.50)
CVA_CAL = (0.015, 0.050, 0.25)
INDEX_DELTA_CAL = (0.040, 0.100, 0.45)
STRUCTURE_CAL = (0.080, 0.200, 0.70)
TEXTURE_CAL = (0.005, 0.020, 0.15)

# Percentile treated as "the top of the change population" when adapting the
# saturation span.
SATURATION_PERCENTILE = 98.0

STRUCTURE_STABILISER = 9e-4  # SSIM's C2 for [0, 1] imagery
DEFAULT_CONTEXT_RADIUS = 3


@dataclass
class EvidenceLayer:
    """One independent line of evidence over the analysis grid."""

    name: str
    probability: np.ndarray      # (H, W) in [0, 1]
    weight: float                # prior importance of this evidence type
    reliability: float           # [0, 1] — how trustworthy it is for this pair
    detail: str                  # analyst-readable justification
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def effective_weight(self) -> float:
        return float(self.weight * self.reliability)

    def summary(self, valid: Optional[np.ndarray] = None, threshold: float = 0.5) -> Dict[str, Any]:
        probability = self.probability
        sample = probability[valid] if valid is not None and np.any(valid) else probability.ravel()
        if sample.size == 0:
            sample = np.zeros(1, dtype=np.float32)
        return {
            "name": self.name,
            "weight": round(float(self.weight), 4),
            "reliability": round(float(self.reliability), 4),
            "effective_weight": round(self.effective_weight, 4),
            "mean_probability": round(float(sample.mean()), 4),
            "p95_probability": round(float(np.percentile(sample, 95)), 4),
            "changed_fraction": round(float((sample > threshold).mean()), 4),
            "detail": self.detail,
            "stats": self.stats,
        }


def robust_probability(
    diff: np.ndarray,
    floor: float,
    scale: float,
    scale_max: Optional[float] = None,
    valid: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Turn a raw difference map into a calibrated change probability.

    Two independent judgements are combined:
      * absolute  — is this difference large in the metric's own units?
      * relative  — is it anomalous against the rest of *this* scene?

    `p = p_absolute * (0.5 + 0.5 * p_relative)`, so absolute magnitude sets the
    ceiling (a uniformly flooded tile still scores ~0.5-1.0) while scene-relative
    anomaly sharpens localised change. Deliberately not min-max normalised: a
    min-max map always contains a 1.0 pixel even when nothing changed at all.

    Args:
        diff: raw difference map.
        floor: differences at or below this are not evidence.
        scale: saturation span, or its lower bound when `scale_max` is given.
        scale_max: upper bound for an adaptive span. When supplied the span is
            taken from the scene's own spread (median to the 98th percentile)
            and clamped to [scale, scale_max].
        valid: pixels to draw the scene statistics from.
    """
    diff = np.asarray(diff, dtype=np.float32)
    median, sigma = robust_center_scale(diff, valid)

    span = scale
    if scale_max is not None:
        sample = diff[valid] if valid is not None and np.any(valid) else diff.ravel()
        observed = float(np.percentile(sample, SATURATION_PERCENTILE)) - median if sample.size else 0.0
        span = float(np.clip(observed, scale, scale_max))

    z = (diff - median) / sigma
    p_relative = 1.0 / (1.0 + np.exp(-(z - ANOMALY_Z_MIDPOINT) / ANOMALY_Z_SOFTNESS))
    p_absolute = np.clip((diff - floor) / max(span, EPS), 0.0, 1.0)
    return (p_absolute * (0.5 + 0.5 * p_relative)).astype(np.float32)


# ---------------------------------------------------------------------------
# 1. Deep EO feature divergence
# ---------------------------------------------------------------------------
def deep_feature_difference(
    before_features: np.ndarray,
    after_features: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compare two patch-token feature grids.

    Returns (cosine_distance, relative_magnitude_change), both on the feature
    grid. Cosine distance captures *what* the patch looks like semantically and
    is invariant to overall gain; the magnitude term captures activation
    strength, which cosine alone discards. Raises when the two grids do not
    describe the same feature space.
    """
    before = np.asarray(before_features, dtype=np.float32)
    after = np.asarray(after_features, dtype=np.float32)

    if before.ndim == 2:
        before = before[:, :, None]
    if after.ndim == 2:
        after = after[:, :, None]
    if before.ndim != 3 or after.ndim != 3:
        raise ValueError(f"feature shapes do not match: {before.shape} vs {after.shape}")
    if before.shape[-1] != after.shape[-1]:
        raise ValueError(
            f"feature shapes do not match: {before.shape} vs {after.shape} — "
            "before/after must come from the same extractor"
        )

    if before.shape[:2] != after.shape[:2]:
        height = max(before.shape[0], after.shape[0])
        width = max(before.shape[1], after.shape[1])
        before = resize_to(before, height, width)
        after = resize_to(after, height, width)

    before_norm = np.linalg.norm(before, axis=-1)
    after_norm = np.linalg.norm(after, axis=-1)
    before_unit = before / (before_norm[..., None] + EPS)
    after_unit = after / (after_norm[..., None] + EPS)

    # 0.5 * (1 - cos) maps the cosine distance onto [0, 1].
    cosine = 0.5 * (1.0 - np.sum(before_unit * after_unit, axis=-1))
    magnitude = np.abs(before_norm - after_norm) / (np.maximum(before_norm, after_norm) + EPS)
    return np.clip(cosine, 0.0, 1.0).astype(np.float32), np.clip(magnitude, 0.0, 1.0).astype(np.float32)


def deep_evidence(
    before_features: np.ndarray,
    after_features: np.ndarray,
    shape: Tuple[int, int],
    valid: Optional[np.ndarray] = None,
    is_placeholder: bool = False,
    model_name: str = "unknown",
    weight: float = 0.45,
) -> EvidenceLayer:
    """Deep feature divergence, upsampled from the patch grid to the analysis grid."""
    cosine, magnitude = deep_feature_difference(before_features, after_features)
    grid_h, grid_w = cosine.shape[:2]

    cosine_full = resize_to(cosine, shape[0], shape[1])
    magnitude_full = resize_to(magnitude, shape[0], shape[1])

    p_cosine = robust_probability(cosine_full, *DEEP_COSINE_CAL, valid=valid)
    p_magnitude = robust_probability(magnitude_full, *DEEP_MAGNITUDE_CAL, valid=valid)
    probability = np.clip(0.75 * p_cosine + 0.25 * p_magnitude, 0.0, 1.0)

    # A statistical stand-in for Prithvi carries real but much weaker semantics,
    # so it must not be allowed to dominate the fusion on its own.
    reliability = 0.5 if is_placeholder else 1.0
    detail = (
        f"Patch-token divergence from {model_name} over a {grid_h}x{grid_w} grid "
        f"(mean cosine distance {float(cosine.mean()):.4f})."
    )
    if is_placeholder:
        detail += " Statistical placeholder features — layer downweighted."

    return EvidenceLayer(
        name="deep_feature",
        probability=probability,
        weight=weight,
        reliability=reliability,
        detail=detail,
        stats={
            "model": model_name,
            "is_placeholder": bool(is_placeholder),
            "feature_grid": [int(grid_h), int(grid_w)],
            "mean_cosine_distance": round(float(cosine.mean()), 5),
            "p95_cosine_distance": round(float(np.percentile(cosine, 95)), 5),
            "mean_magnitude_change": round(float(magnitude.mean()), 5),
        },
    )


# ---------------------------------------------------------------------------
# 2. Spectral divergence
# ---------------------------------------------------------------------------
def _shared_band_stack(
    raster: np.ndarray,
    band_map: Optional[Dict[str, int]],
    names: Tuple[str, ...],
) -> np.ndarray:
    if band_map:
        planes = [raster[..., band_map[name]] for name in names]
        return np.stack(planes, axis=-1).astype(np.float32)
    channels = min(raster.shape[-1], len(names))
    return raster[..., :channels].astype(np.float32)


def change_vector_magnitude(
    before_raster: np.ndarray,
    after_raster: np.ndarray,
    before_map: Optional[Dict[str, int]] = None,
    after_map: Optional[Dict[str, int]] = None,
) -> Tuple[np.ndarray, Tuple[str, ...]]:
    """
    Change Vector Analysis magnitude over the bands both observations share.

    CVA is the classical multispectral change detector: the Euclidean length of
    the per-pixel spectral difference vector. Computed as an RMS over bands so
    its units stay comparable to reflectance regardless of how many bands the
    pair has in common.
    """
    candidates = ("blue", "green", "red", "nir", "swir1", "swir2")
    if before_map and after_map:
        shared = tuple(
            name
            for name in candidates
            if name in before_map
            and name in after_map
            and before_map[name] < before_raster.shape[-1]
            and after_map[name] < after_raster.shape[-1]
        )
    else:
        shared = ()

    if shared:
        before = _shared_band_stack(before_raster, {n: before_map[n] for n in shared}, shared)
        after = _shared_band_stack(after_raster, {n: after_map[n] for n in shared}, shared)
    else:
        channels = min(before_raster.shape[-1], after_raster.shape[-1], 3)
        before = before_raster[..., :channels].astype(np.float32)
        after = after_raster[..., :channels].astype(np.float32)
        shared = tuple(f"band_{i}" for i in range(channels))

    delta = after - before
    return np.sqrt(np.mean(delta * delta, axis=-1)).astype(np.float32), shared


def spectral_evidence(
    before_raster: np.ndarray,
    after_raster: np.ndarray,
    before_indices: SpectralIndices,
    after_indices: SpectralIndices,
    before_map: Optional[Dict[str, int]] = None,
    after_map: Optional[Dict[str, int]] = None,
    valid: Optional[np.ndarray] = None,
    weight: float = 0.35,
) -> Tuple[EvidenceLayer, Dict[str, np.ndarray]]:
    """
    Physical spectral change: CVA magnitude plus normalised-index shift.

    Returns the layer and the signed per-pixel index deltas, which downstream
    change typing needs to tell construction from clearance from water.
    """
    height, width = before_raster.shape[:2]

    cva, shared_bands = change_vector_magnitude(before_raster, after_raster, before_map, after_map)
    cva = resize_to(cva, height, width)

    d_ndvi = resize_to(after_indices.ndvi, height, width) - resize_to(before_indices.ndvi, height, width)
    d_ndwi = resize_to(after_indices.ndwi, height, width) - resize_to(before_indices.ndwi, height, width)
    d_ndbi = resize_to(after_indices.ndbi, height, width) - resize_to(before_indices.ndbi, height, width)
    index_shift = np.maximum(np.maximum(np.abs(d_ndvi), np.abs(d_ndwi)), np.abs(d_ndbi))

    p_cva = robust_probability(cva, *CVA_CAL, valid=valid)
    p_index = robust_probability(index_shift, *INDEX_DELTA_CAL, valid=valid)
    probability = np.clip(0.45 * p_cva + 0.55 * p_index, 0.0, 1.0)

    multispectral = bool(before_indices.is_multispectral and after_indices.is_multispectral)
    reliability = 1.0 if multispectral else 0.55
    detail = (
        f"Change vector analysis over {len(shared_bands)} shared band(s) "
        f"({', '.join(shared_bands)}) with NDVI/NDWI/NDBI shift."
    )
    if not multispectral:
        detail += " RGB index proxies only (no NIR/SWIR) — layer downweighted."

    layer = EvidenceLayer(
        name="spectral",
        probability=probability,
        weight=weight,
        reliability=reliability,
        detail=detail,
        stats={
            "shared_bands": list(shared_bands),
            "is_multispectral": multispectral,
            "mean_cva": round(float(cva.mean()), 5),
            "p95_cva": round(float(np.percentile(cva, 95)), 5),
            "mean_abs_index_shift": round(float(index_shift.mean()), 5),
        },
    )
    return layer, {"d_ndvi": d_ndvi, "d_ndwi": d_ndwi, "d_ndbi": d_ndbi, "cva": cva}


# ---------------------------------------------------------------------------
# 3. Spatial / context consistency
# ---------------------------------------------------------------------------
def spatial_evidence(
    before_raster: np.ndarray,
    after_raster: np.ndarray,
    valid: Optional[np.ndarray] = None,
    radius: int = DEFAULT_CONTEXT_RADIUS,
    weight: float = 0.20,
) -> EvidenceLayer:
    """
    Structural and textural change, independent of brightness and contrast.

    The structural term is SSIM's structure/contrast component: a local window
    whose before/after covariance collapses relative to its variances has been
    physically rearranged, not merely re-illuminated. The texture term compares
    local gradient energy, which rises when built structure or road edges
    appear and stays flat under seasonal colour shift. Neither term can be
    tripped by a global gain or offset difference, which makes this layer the
    natural adjudicator when deep and spectral evidence disagree.
    """
    height, width = before_raster.shape[:2]
    before_gray = to_gray(before_raster)
    after_gray = to_gray(np.asarray(after_raster, dtype=np.float32))
    if after_gray.shape != before_gray.shape:
        after_gray = resize_to(after_gray, height, width)

    _, _, var_b, var_a, cov = local_structure_stats(before_gray, after_gray, radius, valid)
    structural_dissimilarity = 1.0 - (2.0 * cov + STRUCTURE_STABILISER) / (
        var_b + var_a + STRUCTURE_STABILISER
    )
    structural_dissimilarity = np.clip(structural_dissimilarity, 0.0, 1.0)

    texture_before = box_mean(gradient_magnitude(before_gray), radius, valid)
    texture_after = box_mean(gradient_magnitude(after_gray), radius, valid)
    texture_change = np.abs(texture_after - texture_before)

    p_structure = robust_probability(structural_dissimilarity, *STRUCTURE_CAL, valid=valid)
    p_texture = robust_probability(texture_change, *TEXTURE_CAL, valid=valid)
    probability = np.clip(0.65 * p_structure + 0.35 * p_texture, 0.0, 1.0)

    return EvidenceLayer(
        name="spatial_context",
        probability=probability,
        weight=weight,
        reliability=0.9,
        detail=(
            f"Local structural dissimilarity and texture-energy change over a "
            f"{2 * radius + 1}x{2 * radius + 1} window — invariant to illumination and gain."
        ),
        stats={
            "window_px": int(2 * radius + 1),
            "mean_structural_dissimilarity": round(float(structural_dissimilarity.mean()), 5),
            "mean_texture_change": round(float(texture_change.mean()), 5),
        },
    )


def context_support(probability: np.ndarray, threshold: float, radius: int = DEFAULT_CONTEXT_RADIUS) -> np.ndarray:
    """
    Fraction of a pixel's neighbourhood that also exceeds `threshold`.

    Real ground change is spatially contiguous; sensor noise, speckle and
    single-pixel registration error are not. Used by the suppression stage.
    """
    return box_mean((np.asarray(probability) > threshold).astype(np.float32), radius)
