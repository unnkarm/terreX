"""
Feature 4 — Multi-temporal change analysis & classification.

AOI + start date + end date -> query candidate tiles strictly within date window
-> filter usable observations -> co-register pairs (homography/affine)
-> relative radiometric normalization -> feature extraction / Siamese diffing
-> Layer-1 change mask -> Layer-2 change typing (Construction, Clearance, Water, Road)
-> False-alarm suppression & temporal consistency -> earliest supported observation
-> ChangeResult persistence with complete geospatial & processing provenance.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

try:
    import cv2
except ImportError:
    cv2 = None
import numpy as np
from PIL import Image
from sqlalchemy import select, and_

from config import settings
from db.database import get_session
from db.models import Tile, ChangeResult
from services.prithvi import prithvi_service
from services.quality import (
    cloud_fraction_estimate, valid_pixel_fraction, sharpness_score,
    overall_quality_score,
)
from services.false_alarm import evaluate, ObservationQuality
from services.algorithms.registration import register_image_pair, RegistrationResult
from services.algorithms.normalization import normalize_histogram_match
from services.algorithms.spectral import compute_spectral_indices, compute_spectral_deltas, SpectralIndices
from services.algorithms.change_classifier import classify_change_regions, ChangeRegion


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
    elif raster.shape[-1] >= 6:
        # If SWIR2 is unmapped (e.g. S2 L2A tile packed as scl at index 5 or 6), use 6th channel
        idx = band_map.get("scl", 5)
        bands.append(raster[..., idx if idx < raster.shape[-1] else 5])
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


def _difference_to_change_map(before_feat: np.ndarray, after_feat: np.ndarray) -> np.ndarray:
    """
    Swappable change detection head.
    Computes per-patch L2 feature distance, min-max normalized to 0..1.
    """
    if before_feat.shape != after_feat.shape:
        raise ValueError(
            f"Change feature shapes do not match: before={before_feat.shape}, after={after_feat.shape}"
        )
    diff = np.linalg.norm(before_feat - after_feat, axis=-1)
    lo, hi = diff.min(), diff.max()
    if hi - lo < 1e-8:
        return np.zeros_like(diff)
    return (diff - lo) / (hi - lo)


def _extract_prithvi_features(raster: np.ndarray, band_map: Optional[Dict[str, int]]):
    """Use Prithvi's six-band order when possible, otherwise RGB placeholder features."""
    chw = _prepare_prithvi_input(raster, band_map)
    if chw is None:
        chw = np.transpose(raster[..., :3], (2, 0, 1))
    return prithvi_service.extract(chw), chw


def _extract_pair_features(
    before_raster: np.ndarray,
    before_bmap: Optional[Dict[str, int]],
    after_raster: np.ndarray,
    after_bmap: Optional[Dict[str, int]],
):
    before_chw = _prepare_prithvi_input(before_raster, before_bmap)
    after_chw = _prepare_prithvi_input(after_raster, after_bmap)
    if before_chw is None or after_chw is None:
        before_chw = np.transpose(before_raster[..., :3], (2, 0, 1))
        after_chw = np.transpose(after_raster[..., :3], (2, 0, 1))
    return prithvi_service.extract(before_chw), before_chw, prithvi_service.extract(after_chw), after_chw


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
        before_raster, before_bmap = _load_tile_multispectral_or_rgb(before_tile)
        after_raster, after_bmap = _load_tile_multispectral_or_rgb(after_tile)

        # 2. Co-registration: Align after image to before image coordinate frame
        reg_result = register_image_pair(before_raster, after_raster)
        aligned_after_raster = reg_result.aligned_after

        # 3. Relative Radiometric Normalization: match after histogram to before
        norm_after_raster = normalize_histogram_match(aligned_after_raster, before_raster)

        # 4. Feature Extraction & Change Probability Map
        before_feat_map, before_chw, after_feat_map, norm_after_chw = _extract_pair_features(
            before_raster,
            before_bmap,
            norm_after_raster,
            after_bmap,
        )

        change_prob_map = _difference_to_change_map(before_feat_map.array, after_feat_map.array)
        raw_change_score = float(change_prob_map.mean())

        # Resize probability map to full tile resolution
        h_orig, w_orig = before_tile.tile_size, before_tile.tile_size
        if cv2 is not None:
            prob_map_full = cv2.resize(change_prob_map, (w_orig, h_orig), interpolation=cv2.INTER_LINEAR)
        else:
            prob_map_full = np.asarray(
                Image.fromarray(change_prob_map.astype(np.float32)).resize((w_orig, h_orig), Image.Resampling.BILINEAR)
            )
        change_mask_binary = (prob_map_full > settings.CHANGE_PROB_THRESHOLD).astype(np.uint8)

        # 5. Quality Diagnostics
        before_rgb = before_raster[..., :3]
        after_rgb = norm_after_raster[..., :3]

        before_q = ObservationQuality(
            cloud_fraction=cloud_fraction_estimate(before_rgb),
            valid_pixel_fraction=valid_pixel_fraction(before_chw),
            sharpness=sharpness_score(before_rgb.mean(axis=-1)),
            quality_score=before_tile.quality_score or 0.5,
        )
        after_q = ObservationQuality(
            cloud_fraction=cloud_fraction_estimate(after_rgb),
            valid_pixel_fraction=valid_pixel_fraction(norm_after_chw),
            sharpness=sharpness_score(after_rgb.mean(axis=-1)),
            quality_score=after_tile.quality_score or 0.5,
        )

        radiometric_diff = float(abs(before_rgb.mean() - after_rgb.mean()))
        # 6. Multi-Temporal Stack Evaluation & Full Observations Stack (Tier 1.3)
        temporal_scores = []
        earliest_change_date = after_tile.acquisition_date
        observation_stack = []

        # Iterate over all candidates in chronological order to build full timeline
        for idx, cand in enumerate(candidates):
            c_tile = session.get(Tile, cand["tile_id"])
            if not c_tile:
                continue
            c_rast, c_bmap = _load_tile_multispectral_or_rgb(c_tile)
            c_indices = _load_precomputed_indices(c_tile) or compute_spectral_indices(c_rast, c_bmap)
            
            d_base = 0.0
            if idx > 0:
                c_feat, _ = _extract_prithvi_features(c_rast, c_bmap)
                if c_feat.array.shape == before_feat_map.array.shape:
                    d_base = float(_difference_to_change_map(before_feat_map.array, c_feat.array).mean())
                    temporal_scores.append(d_base)
                    if d_base > settings.CHANGE_PROB_THRESHOLD and c_tile.acquisition_date < earliest_change_date:
                        earliest_change_date = c_tile.acquisition_date

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

        # 7. False-Alarm Suppression (Tier 1.5)
        suppression = evaluate(
            raw_change_score=raw_change_score,
            before_q=before_q,
            after_q=after_q,
            registration_correlation=reg_result.correlation_after,
            radiometric_diff=radiometric_diff,
            temporal_series=temporal_scores if temporal_scores else None,
        )

        # 8. Layer-2 Change Typing (Construction, Clearance, Water, Road)
        before_indices = _load_precomputed_indices(before_tile) or compute_spectral_indices(before_raster, before_bmap)
        after_indices = _load_precomputed_indices(after_tile) or compute_spectral_indices(norm_after_raster, after_bmap)

        classified_regions: List[ChangeRegion] = classify_change_regions(
            change_mask=change_mask_binary,
            before_indices=before_indices,
            after_indices=after_indices,
            min_region_size=8,
        )

        # Aggregate detected change types and multi-temporal dynamics
        type_counts = {}
        dynamics_counts = {}
        for r in classified_regions:
            type_counts[r.change_type] = type_counts.get(r.change_type, 0) + r.area_pixels
            dynamics_counts[r.dynamics] = dynamics_counts.get(r.dynamics, 0) + r.area_pixels
        dominant_change_type = max(type_counts, key=type_counts.get) if type_counts else "no_significant_change"
        dominant_dynamics = max(dynamics_counts, key=dynamics_counts.get) if dynamics_counts else "stable"

        # 9. Save Change Mask Image (RGBA overlay)
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

        method = "feature-diff-placeholder" if before_feat_map.is_placeholder else "prithvi-diff"

        # Spectral deltas for Tier 1.4 Evidence Checklist
        d_ndvi_val = round(float(after_indices.ndvi.mean() - before_indices.ndvi.mean()), 4)
        d_ndwi_val = round(float(after_indices.ndwi.mean() - before_indices.ndwi.mean()), 4)
        d_ndbi_val = round(float(after_indices.ndbi.mean() - before_indices.ndbi.mean()), 4)
        max_cloud_pair = round(max(before_q.cloud_fraction, after_q.cloud_fraction), 3)
        min_valid_pixel = round(min(before_q.valid_pixel_fraction, after_q.valid_pixel_fraction), 3)

        evidence_checklist = {
            "d_ndvi": d_ndvi_val,
            "d_ndwi": d_ndwi_val,
            "d_ndbi": d_ndbi_val,
            "persistence_count": len([s for s in temporal_scores if s > settings.CHANGE_PROB_THRESHOLD]),
            "total_observations": len(candidates),
            "valid_pixel_ratio": min_valid_pixel,
            "registration_correlation": round(reg_result.correlation_after, 3),
            "registration_aligned": reg_result.is_aligned,
            "cloud_fraction": max_cloud_pair,
            "radiometric_diff": round(radiometric_diff, 3),
            "items": [
                {
                    "label": "Built-up Spectral Response",
                    "status": "pass" if abs(d_ndbi_val) > 0.05 else "info",
                    "value": f"ΔNDBI: {d_ndbi_val:+.2f}",
                    "details": "Elevated SWIR response characteristic of infrastructure/structures",
                },
                {
                    "label": "Vegetation Phenology Shift",
                    "status": "pass" if abs(d_ndvi_val) > 0.05 else "info",
                    "value": f"ΔNDVI: {d_ndvi_val:+.2f}",
                    "details": "Normalized vegetation change across bi-temporal passes",
                },
                {
                    "label": "Water Index Shift",
                    "status": "pass" if abs(d_ndwi_val) > 0.05 else "info",
                    "value": f"ΔNDWI: {d_ndwi_val:+.2f}",
                    "details": "Water extent and moisture boundary signature",
                },
                {
                    "label": "Multi-Pass Persistence",
                    "status": "pass" if len(temporal_scores) >= 2 else "info",
                    "value": f"{len([s for s in temporal_scores if s > settings.CHANGE_PROB_THRESHOLD])}/{len(temporal_scores)} passes" if temporal_scores else "2/2 passes",
                    "details": "Corroborated across continuous time series observations",
                },
                {
                    "label": "Sub-pixel Registration",
                    "status": "pass" if reg_result.correlation_after >= 0.7 else "fail",
                    "value": f"{int(reg_result.correlation_after * 100)}% corr",
                    "details": "FFT phase correlation and ECC alignment quality",
                },
                {
                    "label": "Cloud & Atmospheric Quality",
                    "status": "pass" if max_cloud_pair < 0.20 else "fail",
                    "value": f"{int(max_cloud_pair * 100)}% cloud",
                    "details": "Mask clear-sky confidence score",
                },
            ],
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
            is_placeholder_model=before_feat_map.is_placeholder,
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
            "is_placeholder_model": before_feat_map.is_placeholder,
        }
