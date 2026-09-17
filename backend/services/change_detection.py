"""
Feature 4 — Multi-temporal change analysis & classification.

AOI + start date + end date -> query candidate tiles strictly within date window
-> filter usable observations -> run the multi-evidence change pipeline
(services.algorithms.pipeline) over the selected before/after pair:

    Registration -> radiometric normalization -> cloud/quality masking
    -> Prithvi EO features -> deep feature difference
    -> spectral differences -> spatial/context consistency
    -> evidence fusion -> false-alarm suppression
    -> change mask -> change type -> confidence

-> corroborate across the rest of the observation stack -> scene-level
false-alarm scoring -> earliest supported observation -> ChangeResult
persistence with complete geospatial & processing provenance.

This module owns the database, file and API concerns only. Every array
operation lives in services.algorithms, which is importable and testable
without a database.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import numpy as np
from PIL import Image
from sqlalchemy import select, and_

from config import settings
from db.database import get_session
from db.models import Tile, ChangeResult
from services.prithvi import prithvi_service
from services.quality import valid_pixel_fraction, sharpness_score
from services.false_alarm import evaluate, ObservationQuality
from services.algorithms.pipeline import (
    PIPELINE_VERSION,
    ChangeAnalysis,
    Observation,
    analyze_change_pair,
)
from services.algorithms.spectral import compute_spectral_indices, SpectralIndices
from services.algorithms.change_classifier import ChangeRegion
from services.algorithms.evidence import deep_feature_difference

# Beyond this many observations the corroboration pass stops running the full
# pipeline per date; the timeline itself is still built from every observation.
MAX_CORROBORATION_PASSES = 12


def _load_tile_rgb_chw(tile: Tile) -> np.ndarray:
    """Load RGB thumbnail as float32 [0, 1] CHW array."""
    img = Image.open(tile.tile_path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return np.transpose(arr, (2, 0, 1))  # (3, H, W)


def _load_tile_multispectral_or_rgb(tile: Tile) -> Tuple[np.ndarray, Optional[Dict[str, int]]]:
    """
    Attempt to load high-fidelity multispectral .npz pack;
    fall back to RGB thumbnail if .npz is not present.
    Returns (array (H, W, C) float32 [0, 1], band_map).
    """
    thumb_path = Path(tile.tile_path)
    npz_path = thumb_path.with_suffix(".npz")
    if npz_path.exists():
        try:
            data = np.load(npz_path, allow_pickle=True)
            bands = data["bands"]  # (C, H, W)
            band_map = data["band_map"].item() if "band_map" in data else None
            # Normalize to float32 [0, 1]
            if bands.max() > 1.0:
                bands = bands / (255.0 if bands.max() <= 255.0 else 10000.0)
            bands_hwc = np.transpose(bands, (1, 2, 0))
            return bands_hwc, band_map
        except Exception:
            pass

    # Fallback to RGB
    rgb_chw = _load_tile_rgb_chw(tile)
    rgb_hwc = np.transpose(rgb_chw, (1, 2, 0))
    return rgb_hwc, {"red": 0, "green": 1, "blue": 2}


def _load_precomputed_indices(tile: Tile) -> Optional[SpectralIndices]:
    """Load ingest-time spectral index maps when available."""
    try:
        data = np.load(Path(tile.tile_path).with_suffix(".npz"), allow_pickle=True)
        if all(key in data for key in ("ndvi", "ndwi", "ndbi")):
            band_map = data["band_map"].item() if "band_map" in data else {}
            return SpectralIndices(data["ndvi"], data["ndwi"], data["ndbi"], "nir" in band_map, band_map)
    except Exception:
        pass
    return None


def _load_observation(tile: Tile) -> Observation:
    """
    Build a pipeline Observation from a tile, carrying every ancillary plane
    the tile pack has: the raw scene-classification band (unscaled, so its
    class codes survive), the ingest-time quality mask, and the precomputed
    spectral indices.
    """
    raster, band_map = _load_tile_multispectral_or_rgb(tile)
    scl: Optional[np.ndarray] = None
    ingest_mask: Optional[np.ndarray] = None

    npz_path = Path(tile.tile_path).with_suffix(".npz")
    if npz_path.exists():
        try:
            data = np.load(npz_path, allow_pickle=True)
            if "quality_mask" in data:
                ingest_mask = np.asarray(data["quality_mask"]).astype(bool)
            stored_map = data["band_map"].item() if "band_map" in data else {}
            scl_index = stored_map.get("scl") if isinstance(stored_map, dict) else None
            if scl_index is not None and "bands" in data:
                raw_bands = data["bands"]
                if 0 <= int(scl_index) < raw_bands.shape[0]:
                    # Read before any [0, 1] rescaling — SCL carries class codes,
                    # not reflectance, and dividing by 10000 would destroy them.
                    scl = np.asarray(raw_bands[int(scl_index)])
        except Exception:
            pass

    return Observation(
        raster=raster,
        band_map=band_map,
        scl=scl,
        ingest_mask=ingest_mask,
        indices=_load_precomputed_indices(tile),
        label=tile.acquisition_date.strftime("%Y-%m-%d") if tile.acquisition_date else str(tile.tile_id),
    )


def _prepare_prithvi_input(raster: np.ndarray, band_map: Optional[Dict[str, int]]) -> Optional[np.ndarray]:
    """Arrange TerreX multispectral data into Prithvi's six-band input order."""
    if not band_map:
        return None
    required = ("blue", "green", "red", "nir", "swir1")
    if any(name not in band_map or band_map[name] >= raster.shape[-1] for name in required):
        return None

    bands = [raster[..., band_map[name]] for name in required]
    if "swir2" in band_map and band_map["swir2"] < raster.shape[-1]:
        bands.append(raster[..., band_map["swir2"]])
    else:
        return None

    return np.stack(bands, axis=0)


def _tile_has_prithvi_bands(tile: Tile) -> bool:
    """Return whether the tile pack can feed the six-band Prithvi path."""
    try:
        data = np.load(Path(tile.tile_path).with_suffix(".npz"), allow_pickle=True)
        if "bands" not in data or "band_map" not in data:
            return False
        band_map = data["band_map"].item()
        return _prepare_prithvi_input(np.transpose(data["bands"], (1, 2, 0)), band_map) is not None
    except Exception:
        return False


def _to_rgb_chw(raster: np.ndarray) -> np.ndarray:
    """Three-channel CHW view of a raster, for the non-six-band Prithvi path."""
    return np.transpose(raster[..., : min(3, raster.shape[-1])], (2, 0, 1))


def _difference_to_change_map(before_feat: np.ndarray, after_feat: np.ndarray) -> np.ndarray:
    """
    Deep-feature change head.

    Kept as the single-layer view of the deep evidence: per-patch cosine
    distance blended with relative activation-magnitude change, calibrated to
    [0, 1]. Note this is only *one* of the evidence layers the pipeline fuses —
    see services.algorithms.pipeline for the full detector.

    Raises ValueError when the two feature maps do not describe the same
    feature space, since differencing them would be meaningless.
    """
    cosine, magnitude = deep_feature_difference(before_feat, after_feat)
    combined = 0.75 * cosine + 0.25 * magnitude
    return np.clip(combined, 0.0, 1.0).astype(np.float32)


def _extract_prithvi_features(raster: np.ndarray, band_map: Optional[Dict[str, int]]):
    """Use Prithvi's six-band order when possible, otherwise RGB placeholder features."""
    chw = _prepare_prithvi_input(raster, band_map)
    if chw is None:
        chw = _to_rgb_chw(raster)
    return prithvi_service.extract(chw), chw


def _extract_pair_features(
    before_raster: np.ndarray,
    before_bmap: Optional[Dict[str, int]],
    after_raster: np.ndarray,
    after_bmap: Optional[Dict[str, int]],
):
    """
    Extract features for both dates in a single, consistent feature space.

    If either side cannot supply Prithvi's six ordered bands, *both* fall back
    to the three-band path. Mixing a six-band feature map with a three-band one
    would difference two different representations and report the mismatch as
    ground change.
    """
    before_chw = _prepare_prithvi_input(before_raster, before_bmap)
    after_chw = _prepare_prithvi_input(after_raster, after_bmap)
    if before_chw is None or after_chw is None:
        before_chw = _to_rgb_chw(before_raster)
        after_chw = _to_rgb_chw(after_raster)
    return prithvi_service.extract(before_chw), before_chw, prithvi_service.extract(after_chw), after_chw


def _make_pair_feature_extractor(
    before_raster: np.ndarray,
    before_bmap: Optional[Dict[str, int]],
    after_raster: np.ndarray,
    after_bmap: Optional[Dict[str, int]],
):
    """
    Build the feature-extractor callable the pipeline injects into its deep
    evidence layer, locked to one representation for the whole pair.
    """
    six_band = (
        _prepare_prithvi_input(before_raster, before_bmap) is not None
        and _prepare_prithvi_input(after_raster, after_bmap) is not None
    )

    def extractor(raster: np.ndarray, band_map: Optional[Dict[str, int]]):
        chw = _prepare_prithvi_input(raster, band_map) if six_band else None
        if chw is None:
            chw = _to_rgb_chw(raster)
        feature_map = prithvi_service.extract(chw)
        return feature_map.array, feature_map.model_name, feature_map.is_placeholder

    return extractor


def _method_label(analysis: ChangeAnalysis) -> str:
    """Human-readable detector identity persisted alongside every result."""
    if not analysis.deep_available:
        return f"{PIPELINE_VERSION}/spectral-spatial"
    if analysis.deep_is_placeholder:
        return f"{PIPELINE_VERSION}/placeholder-features"
    if analysis.feature_model == "prithvi-int8-onnx":
        return f"{PIPELINE_VERSION}/prithvi-onnx"
    return f"{PIPELINE_VERSION}/{analysis.feature_model}"


def _parse_date(date_val: Any) -> Optional[datetime]:
    if isinstance(date_val, datetime):
        return date_val
    if not date_val:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(str(date_val)[:19], fmt)
        except ValueError:
            continue
    return None
def find_candidate_tiles(
    lon: float,
    lat: float,
    date_from: str,
    date_to: str,
    tolerance_deg: float = 0.08,
    min_quality: float = 0.25,
    reference_tile_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find usable observations for an AOI strictly within [date_from, date_to].
    Filters out observations with low quality or missing timestamps.
    If reference_tile_id or exact coordinates are provided, prioritizes matching
    the exact same spatial grid cell (col_off, row_off or minimum distance).
    """
    dt_from = _parse_date(date_from)
    dt_to = _parse_date(date_to)

    # If date_to was just a date (YYYY-MM-DD), make it inclusive to the end of that day
    if dt_to and len(str(date_to)) == 10:
        dt_to = dt_to.replace(hour=23, minute=59, second=59)

    with get_session() as session:
        ref_tile = None
        if reference_tile_id:
            ref_tile = session.get(Tile, reference_tile_id)
            if ref_tile:
                lon = ref_tile.lon
                lat = ref_tile.lat

        query = select(Tile).where(
            and_(
                Tile.lon.between(lon - tolerance_deg, lon + tolerance_deg),
                Tile.lat.between(lat - tolerance_deg, lat + tolerance_deg),
            )
        )
        if dt_from is not None:
            query = query.where(Tile.acquisition_date >= dt_from)
        if dt_to is not None:
            query = query.where(Tile.acquisition_date <= dt_to)

        rows = session.execute(query).scalars().all()

        candidates = []
        for t in rows:
            if not t.acquisition_date:
                continue
            # Gate on minimal quality
            q = t.quality_score if t.quality_score is not None else 0.5
            c_frac = t.cloud_fraction if t.cloud_fraction is not None else 0.0
            if q < min_quality or c_frac > 0.85:
                continue

            # Calculate distance to query location
            dist = ((t.lon - lon) ** 2 + (t.lat - lat) ** 2) ** 0.5
            candidates.append({
                "tile_id": t.tile_id,
                "scene_id": t.scene_id,
                "lon": t.lon,
                "lat": t.lat,
                "col_off": t.col_off,
                "row_off": t.row_off,
                "dist": dist,
                "acquisition_date": t.acquisition_date,
                "tile_path": t.tile_path,
                "cloud_fraction": c_frac,
                "quality_score": q,
                "sensor": t.sensor,
            })

        if not candidates:
            return []

        # If a reference tile is specified, filter strictly to the exact same grid cell (col_off, row_off)
        if ref_tile is not None:
            exact_cell_cands = [
                c for c in candidates
                if c["col_off"] == ref_tile.col_off and c["row_off"] == ref_tile.row_off
            ]
            if len(exact_cell_cands) >= 2:
                candidates = exact_cell_cands
        else:
            # Group by closest grid cell (minimum distance to the requested lon/lat)
            min_dist = min(c["dist"] for c in candidates)
            cell_cands = [c for c in candidates if c["dist"] <= min_dist + 0.005]
            if len(cell_cands) >= 2:
                candidates = cell_cands

        # Sort chronologically
        candidates.sort(key=lambda c: c["acquisition_date"])
        return candidates


def _status(flag: bool) -> str:
    return "pass" if flag else "fail"


def _build_evidence_checklist(
    analysis: ChangeAnalysis,
    temporal_scores: List[float],
    total_observations: int,
    before_q: ObservationQuality,
    after_q: ObservationQuality,
) -> Dict[str, Any]:
    """
    The analyst-facing evidence checklist.

    Every row is a distinct, independently derived test — that is the whole
    point of the multi-evidence design: a detection is defensible because
    several unrelated measurements agree, not because one embedding moved.
    """
    layer_by_name = {layer.name: layer for layer in analysis.layers}
    summaries = {item["name"]: item for item in analysis.layer_summaries(settings.CHANGE_PROB_THRESHOLD)}

    valid = analysis.joint_valid
    deltas = analysis.index_deltas
    changed = analysis.change_mask.astype(bool)
    # Index deltas are reported over the detected change, not the whole tile:
    # a scene-wide average dilutes a real 2% built-up footprint to nothing.
    footprint = changed if changed.any() else valid
    d_ndvi_val = round(float(deltas["d_ndvi"][footprint].mean()), 4) if footprint.any() else 0.0
    d_ndwi_val = round(float(deltas["d_ndwi"][footprint].mean()), 4) if footprint.any() else 0.0
    d_ndbi_val = round(float(deltas["d_ndbi"][footprint].mean()), 4) if footprint.any() else 0.0

    max_cloud_pair = round(max(before_q.cloud_fraction, after_q.cloud_fraction), 3)
    min_valid_pixel = round(min(before_q.valid_pixel_fraction, after_q.valid_pixel_fraction), 3)
    persistence_count = len([s for s in temporal_scores if s > settings.CHANGE_PROB_THRESHOLD])
    registration = analysis.registration
    agreement = analysis.evidence_agreement

    deep_summary = summaries.get("deep_feature")
    spectral_summary = summaries.get("spectral")
    spatial_summary = summaries.get("spatial_context")

    items: List[Dict[str, Any]] = []

    if deep_summary is not None:
        deep_layer = layer_by_name["deep_feature"]
        # A placeholder extractor is degraded, not failed: the layer ran and was
        # downweighted accordingly, which is an "info" state, not a red cross.
        deep_status = (
            "info" if analysis.deep_is_placeholder
            else _status(deep_summary["changed_fraction"] > 0.005)
        )
        items.append({
            "label": "Deep EO Feature Divergence",
            "status": deep_status,
            "value": f"{deep_summary['changed_fraction'] * 100:.1f}% of tile",
            "details": deep_layer.detail,
        })
    else:
        items.append({
            "label": "Deep EO Feature Divergence",
            "status": "info",
            "value": "unavailable",
            "details": "No EO feature extractor available; detection rests on spectral and spatial evidence.",
        })

    items.append({
        "label": "Built-up Spectral Response",
        "status": _status(abs(d_ndbi_val) > 0.05),
        "value": f"ΔNDBI: {d_ndbi_val:+.2f}",
        "details": "Elevated SWIR response characteristic of infrastructure/structures",
    })
    items.append({
        "label": "Vegetation Phenology Shift",
        "status": _status(abs(d_ndvi_val) > 0.05),
        "value": f"ΔNDVI: {d_ndvi_val:+.2f}",
        "details": "Normalized vegetation change across bi-temporal passes",
    })
    items.append({
        "label": "Water Index Shift",
        "status": _status(abs(d_ndwi_val) > 0.05),
        "value": f"ΔNDWI: {d_ndwi_val:+.2f}",
        "details": "Water extent and moisture boundary signature",
    })

    if spatial_summary is not None:
        items.append({
            "label": "Spatial Structure Consistency",
            "status": _status(spatial_summary["changed_fraction"] > 0.002),
            "value": f"{spatial_summary['changed_fraction'] * 100:.1f}% of tile",
            "details": layer_by_name["spatial_context"].detail,
        })

    items.append({
        "label": "Multi-Evidence Agreement",
        "status": _status(agreement >= 0.5),
        "value": f"{agreement * 100:.0f}% weighted",
        "details": (
            f"Independent evidence layers ({', '.join(analysis.fusion.layer_names)}) fused with "
            f"reliability weights {analysis.fusion.summary(valid)['weights']}."
        ),
    })
    items.append({
        "label": "Multi-Pass Persistence",
        "status": _status(persistence_count >= 1 and len(temporal_scores) >= 1),
        "value": (
            f"{persistence_count}/{len(temporal_scores)} passes" if temporal_scores
            else f"{total_observations} observation(s)"
        ),
        "details": "Corroborated across continuous time series observations",
    })
    items.append({
        "label": "Sub-pixel Registration",
        "status": _status(registration.is_aligned and registration.residual_shift_px <= 0.5),
        "value": f"{registration.residual_shift_px:.2f}px residual",
        "details": (
            f"Aligned by {registration.method} over {registration.inliers} inliers "
            f"(applied dx={registration.dx:+.2f}px, dy={registration.dy:+.2f}px). "
            f"Scene correlation {registration.correlation_before:.2f} to "
            f"{registration.correlation_after:.2f}; correlation also falls with genuine "
            "change, so alignment is judged on the residual."
        ),
    })
    normalization = analysis.normalization
    mean_gain = sum(normalization.gains) / len(normalization.gains) if normalization.gains else 1.0
    mean_offset = sum(normalization.offsets) / len(normalization.offsets) if normalization.offsets else 0.0
    items.append({
        "label": "Radiometric Normalization",
        "status": _status(normalization.method != "identity"),
        # The fitted transfer is the meaningful figure. The scene-mean shift is
        # not: fitting on invariant pixels deliberately leaves genuine change in
        # place, so a large real change can widen that mean rather than shrink it.
        "value": f"gain x{mean_gain:.2f}, offset {mean_offset:+.3f}",
        "details": normalization.detail,
    })
    items.append({
        "label": "Cloud & Quality Masking",
        "status": _status(analysis.clear_fraction >= 0.6 and max_cloud_pair < 0.20),
        "value": f"{analysis.clear_fraction * 100:.0f}% usable",
        "details": (
            f"Cloud/shadow/nodata masked in both dates "
            f"(before: {analysis.before_mask.method}, after: {analysis.after_mask.method}); "
            f"masked pixels are excluded from every evidence layer."
        ),
    })
    items.append({
        "label": "False-Alarm Suppression",
        "status": _status(analysis.suppression.changed_pixels > 0),
        "value": f"{analysis.suppression.removed_fraction * 100:.0f}% removed",
        "details": "; ".join(stage["detail"] for stage in analysis.suppression.stages),
    })

    return {
        "d_ndvi": d_ndvi_val,
        "d_ndwi": d_ndwi_val,
        "d_ndbi": d_ndbi_val,
        "persistence_count": persistence_count,
        "total_observations": total_observations,
        "valid_pixel_ratio": min_valid_pixel,
        "registration_correlation": round(registration.correlation_after, 3),
        "registration_aligned": registration.is_aligned,
        "cloud_fraction": max_cloud_pair,
        "radiometric_diff": round(float(analysis.radiometric_shift), 3),
        "evidence_agreement": round(float(agreement), 3),
        "clear_fraction": round(float(analysis.clear_fraction), 3),
        "changed_area_fraction": round(float(analysis.changed_fraction), 5),
        "deep_layer_available": analysis.deep_available,
        "deep_layer_is_placeholder": analysis.deep_is_placeholder,
        "spectral_is_multispectral": bool(
            spectral_summary and spectral_summary["stats"].get("is_multispectral")
        ),
        "items": items,
    }


def run_change_detection(
    lon: float,
    lat: float,
    date_from: str,
    date_to: str,
    tile_id: Optional[str] = None,
) -> dict:
    candidates = find_candidate_tiles(lon, lat, date_from, date_to, tolerance_deg=0.08, reference_tile_id=tile_id)
    if len(candidates) < 2:
        candidates = find_candidate_tiles(lon, lat, date_from, date_to, tolerance_deg=0.15, reference_tile_id=tile_id)
    if len(candidates) < 2:
        return {
            "status": "insufficient_data",
            "is_fallback": False,
            "result_source": "backend",
            "message": (
                f"Found {len(candidates)} usable observation(s) in the window {date_from} to {date_to}. "
                "Change detection requires at least 2 usable observations."
            ),
            "candidate_count": len(candidates),
            "earliest_supported_observation": candidates[0]["acquisition_date"].isoformat() if candidates else None,
        }

    with get_session() as session:
        prithvi_ready = [c for c in candidates if session.get(Tile, c["tile_id"]) is not None]
        if len(prithvi_ready) >= 2:
            candidates = prithvi_ready

        # If reference tile was specified, ensure it is one of the pair (before or after)
        ref_in_candidates = None
        if tile_id:
            for c in candidates:
                if c["tile_id"] == tile_id:
                    ref_in_candidates = c
                    break

        if ref_in_candidates is not None:
            # If the reference tile is the latest or in between, pair it with the earliest candidate before it
            earlier_candidates = [c for c in candidates if c["acquisition_date"] < ref_in_candidates["acquisition_date"]]
            later_candidates = [c for c in candidates if c["acquisition_date"] > ref_in_candidates["acquisition_date"]]
            if earlier_candidates:
                before_cand = earlier_candidates[0]
                after_cand = ref_in_candidates
            elif later_candidates:
                before_cand = ref_in_candidates
                after_cand = later_candidates[-1]
            else:
                before_cand, after_cand = candidates[0], candidates[-1]
        else:
            before_cand, after_cand = candidates[0], candidates[-1]

        before_tile = session.get(Tile, before_cand["tile_id"])
        after_tile = session.get(Tile, after_cand["tile_id"])

        # ------------------------------------------------------------------
        # Multi-evidence pipeline over the selected before/after pair.
        # ------------------------------------------------------------------
        before_obs = _load_observation(before_tile)
        after_obs = _load_observation(after_tile)
        extractor = _make_pair_feature_extractor(
            before_obs.raster, before_obs.band_map, after_obs.raster, after_obs.band_map
        )
        analysis = analyze_change_pair(
            before_obs,
            after_obs,
            feature_extractor=extractor,
            threshold=settings.CHANGE_PROB_THRESHOLD,
            weights={
                "deep_feature": settings.W_EVIDENCE_DEEP,
                "spectral": settings.W_EVIDENCE_SPECTRAL,
                "spatial_context": settings.W_EVIDENCE_SPATIAL,
            },
            context_radius=settings.CHANGE_CONTEXT_RADIUS,
            min_region_pixels=settings.CHANGE_MIN_REGION_PIXELS,
            cloud_dilation=settings.CLOUD_MASK_DILATION,
        )

        before_raster = before_obs.raster
        norm_after_raster = analysis.normalized_after
        reg_result = analysis.registration
        prob_map_full = analysis.change_probability
        change_mask_binary = analysis.change_mask
        raw_change_score = analysis.raw_change_score

        # Quality diagnostics for the scene-level scorer.
        before_rgb = before_raster[..., :3]
        after_rgb = norm_after_raster[..., :3]
        before_q = ObservationQuality(
            cloud_fraction=1.0 - analysis.before_mask.clear_fraction,
            valid_pixel_fraction=valid_pixel_fraction(np.transpose(before_raster, (2, 0, 1))),
            sharpness=sharpness_score(before_rgb.mean(axis=-1)),
            quality_score=before_tile.quality_score or 0.5,
        )
        after_q = ObservationQuality(
            cloud_fraction=1.0 - analysis.after_mask.clear_fraction,
            valid_pixel_fraction=valid_pixel_fraction(np.transpose(norm_after_raster, (2, 0, 1))),
            sharpness=sharpness_score(after_rgb.mean(axis=-1)),
            quality_score=after_tile.quality_score or 0.5,
        )
        radiometric_diff = float(analysis.radiometric_shift)

        # ------------------------------------------------------------------
        # Temporal corroboration across the rest of the observation stack.
        # Each extra date is scored by the same multi-evidence pipeline, so
        # persistence means "several independent evidence types agreed again",
        # not "the embedding moved again".
        # ------------------------------------------------------------------
        temporal_scores: List[float] = []
        earliest_change_date = after_tile.acquisition_date
        observation_stack: List[Dict[str, Any]] = []
        corroboration_budget = MAX_CORROBORATION_PASSES

        for idx, cand in enumerate(candidates):
            c_tile = session.get(Tile, cand["tile_id"])
            if not c_tile:
                continue
            c_obs = _load_observation(c_tile)
            c_indices = c_obs.indices or compute_spectral_indices(c_obs.raster, c_obs.band_map)

            d_base = 0.0
            agreement = 0.0
            if idx > 0 and corroboration_budget > 0:
                corroboration_budget -= 1
                try:
                    pass_analysis = analyze_change_pair(
                        before_obs,
                        c_obs,
                        feature_extractor=_make_pair_feature_extractor(
                            before_obs.raster, before_obs.band_map, c_obs.raster, c_obs.band_map
                        ),
                        threshold=settings.CHANGE_PROB_THRESHOLD,
                        weights={
                            "deep_feature": settings.W_EVIDENCE_DEEP,
                            "spectral": settings.W_EVIDENCE_SPECTRAL,
                            "spatial_context": settings.W_EVIDENCE_SPATIAL,
                        },
                        context_radius=settings.CHANGE_CONTEXT_RADIUS,
                        min_region_pixels=settings.CHANGE_MIN_REGION_PIXELS,
                        cloud_dilation=settings.CLOUD_MASK_DILATION,
                    )
                    d_base = float(pass_analysis.raw_change_score)
                    agreement = float(pass_analysis.evidence_agreement)
                    temporal_scores.append(d_base)
                    if (
                        d_base > settings.CHANGE_PROB_THRESHOLD
                        and c_tile.acquisition_date
                        and c_tile.acquisition_date < earliest_change_date
                    ):
                        earliest_change_date = c_tile.acquisition_date
                except Exception:
                    # A single unusable date must not sink the whole timeline.
                    d_base = 0.0

            thumb_name = Path(c_tile.thumbnail_path).name if c_tile.thumbnail_path else "thumb.jpg"
            observation_stack.append({
                "index": idx + 1,
                "tile_id": c_tile.tile_id,
                "scene_id": c_tile.scene_id,
                "acquisition_date": c_tile.acquisition_date.isoformat() if c_tile.acquisition_date else None,
                "date_formatted": c_tile.acquisition_date.strftime("%Y-%m-%d") if c_tile.acquisition_date else "Unknown",
                "year": c_tile.acquisition_date.strftime("%Y") if c_tile.acquisition_date else "N/A",
                "sensor": c_tile.sensor or "Sentinel-2",
                "cloud_fraction": round(c_tile.cloud_fraction or 0.0, 3),
                "quality_score": round(c_tile.quality_score or 0.8, 3),
                "thumbnail_url": f"/static/tiles/{c_tile.scene_id}/{thumb_name}",
                "distance_from_baseline": round(d_base, 3),
                "evidence_agreement": round(agreement, 3),
                "mean_ndvi": round(float(c_indices.ndvi.mean()), 3),
                "mean_ndwi": round(float(c_indices.ndwi.mean()), 3),
                "mean_ndbi": round(float(c_indices.ndbi.mean()), 3),
                "is_baseline": idx == 0,
                "is_earliest_change": False,  # Will flag below
            })

        # Flag earliest supported change node
        for obs in observation_stack:
            if obs["acquisition_date"] and obs["acquisition_date"] == earliest_change_date.isoformat():
                obs["is_earliest_change"] = True

        # ------------------------------------------------------------------
        # Scene-level false-alarm scoring & confidence.
        # ------------------------------------------------------------------
        layer_summaries = analysis.layer_summaries(settings.CHANGE_PROB_THRESHOLD)
        suppression = evaluate(
            raw_change_score=raw_change_score,
            before_q=before_q,
            after_q=after_q,
            registration_correlation=reg_result.correlation_after,
            radiometric_diff=radiometric_diff,
            temporal_series=temporal_scores if temporal_scores else None,
            evidence_agreement=analysis.evidence_agreement,
            evidence_layers=layer_summaries,
            clear_fraction=analysis.clear_fraction,
            radiometry_normalized=analysis.normalization.method != "identity",
            registration_residual_px=reg_result.residual_shift_px,
            registration_aligned=reg_result.is_aligned,
        )

        before_indices = analysis.before_indices
        after_indices = analysis.after_indices
        classified_regions: List[ChangeRegion] = analysis.regions
        region_evidence_map: Dict[int, Dict[str, float]] = {}
        for stage in analysis.stages:
            if stage.name == "change_typing":
                region_evidence_map = stage.metrics.get("region_evidence", {}) or {}
                break

        dominant_change_type = analysis.dominant_change_type
        dominant_dynamics = analysis.dominant_dynamics

        # ------------------------------------------------------------------
        # Persist the change mask overlay.
        # ------------------------------------------------------------------
        mask_dir = settings.TILES_DIR / "change_masks"
        mask_dir.mkdir(parents=True, exist_ok=True)
        mask_filename = f"{before_tile.tile_id}_{after_tile.tile_id}.png"
        mask_path = mask_dir / mask_filename

        mask_img_arr = (prob_map_full * 255).clip(0, 255).astype(np.uint8)
        Image.fromarray(mask_img_arr).save(mask_path)

        # Calculate affected ground area
        pixel_res = before_tile.resolution_m or 10.0
        changed_pixels = int(change_mask_binary.sum())
        total_change_area_m2 = changed_pixels * (pixel_res ** 2)

        method = _method_label(analysis)

        evidence_checklist = _build_evidence_checklist(
            analysis, temporal_scores, len(candidates), before_q, after_q
        )

        pipeline_audit = {
            "version": PIPELINE_VERSION,
            "threshold": settings.CHANGE_PROB_THRESHOLD,
            "stages": analysis.stage_dicts(),
        }

        # Persist ChangeResult
        result = ChangeResult(
            before_tile_id=before_tile.tile_id,
            after_tile_id=after_tile.tile_id,
            change_score=suppression.change_score,
            quality_score=suppression.quality_score,
            confidence=suppression.confidence,
            change_area_m2=round(total_change_area_m2, 1),
            change_mask_path=str(mask_path),
            reasons=suppression.reasons,
            method=method,
            is_placeholder_model=analysis.deep_is_placeholder,
            evidence_layers=layer_summaries,
            pipeline_stages=analysis.stage_dicts(),
        )
        session.add(result)
        session.flush()

        return {
            "status": "ok",
            "is_fallback": False,
            "result_source": "backend",
            "change_id": result.change_id,
            "dominant_change_type": dominant_change_type,
            "dominant_dynamics": dominant_dynamics,
            "change_score": suppression.change_score,
            "quality_score": suppression.quality_score,
            "confidence": suppression.confidence,
            "change_area_m2": round(total_change_area_m2, 1),
            "change_area_hectares": round(total_change_area_m2 / 10000.0, 2),
            "change_summary": f"{round(total_change_area_m2 / 10000.0, 1)} hectares of {dominant_change_type.replace('_', ' ')} ({dominant_dynamics}) detected with {int(suppression.confidence * 100)}% confidence.",
            "change_mask_path": str(mask_path),
            "change_mask_url": f"/static/tiles/change_masks/{mask_filename}",
            "earliest_supported_observation": earliest_change_date.isoformat(),
            "observations": observation_stack,
            "evidence": evidence_checklist,
            "evidence_layers": layer_summaries,
            "fusion": analysis.fusion.summary(analysis.joint_valid),
            "masking": {
                "before": analysis.before_mask.summary(),
                "after": analysis.after_mask.summary(),
                "joint_clear_fraction": round(float(analysis.clear_fraction), 4),
            },
            "normalization": analysis.normalization.summary(),
            "suppression": analysis.suppression.summary(),
            "pipeline": pipeline_audit,
            "confidence_breakdown": suppression.confidence_breakdown,
            "confounds": [
                {
                    "factor": c.factor,
                    "severity": c.severity,
                    "penalty_factor": c.penalty_factor,
                    "explanation": c.explanation,
                }
                for c in suppression.confounds
            ],
            "registration": {
                "is_aligned": reg_result.is_aligned,
                "correlation_before": round(reg_result.correlation_before, 3),
                "correlation_after": round(reg_result.correlation_after, 3),
                "inliers": reg_result.inliers,
                "dx": round(reg_result.dx, 2),
                "dy": round(reg_result.dy, 2),
                "residual_shift_px": round(reg_result.residual_shift_px, 3),
            },
            "change_regions": [
                {
                    "region_id": r.region_id,
                    "change_type": r.change_type,
                    "dynamics": r.dynamics,
                    "confidence": r.confidence,
                    "area_pixels": r.area_pixels,
                    "area_m2": round(r.area_pixels * (pixel_res ** 2), 1),
                    "centroid": r.centroid,
                    "bbox": r.bbox,
                    "mean_d_ndvi": r.mean_d_ndvi,
                    "mean_d_ndwi": r.mean_d_ndwi,
                    "mean_d_ndbi": r.mean_d_ndbi,
                    "elongation": r.elongation,
                    "rationale": r.rationale,
                    "evidence": region_evidence_map.get(r.region_id, {}),
                }
                for r in classified_regions
            ],
            "suppression_reasons": suppression.reasons,
            "before": {
                "tile_id": before_tile.tile_id,
                "acquisition_date": before_tile.acquisition_date.isoformat(),
                "thumbnail_path": before_tile.thumbnail_path,
                "thumbnail_url": f"/static/tiles/{before_tile.scene_id}/{Path(before_tile.thumbnail_path).name}",
                "sensor": before_tile.sensor,
                "quality": before_q.__dict__,
            },
            "after": {
                "tile_id": after_tile.tile_id,
                "acquisition_date": after_tile.acquisition_date.isoformat(),
                "thumbnail_path": after_tile.thumbnail_path,
                "thumbnail_url": f"/static/tiles/{after_tile.scene_id}/{Path(after_tile.thumbnail_path).name}",
                "sensor": after_tile.sensor,
                "quality": after_q.__dict__,
            },
            "method": method,
            "is_placeholder_model": analysis.deep_is_placeholder,
        }
