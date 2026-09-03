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

import cv2
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


def _difference_to_change_map(before_feat: np.ndarray, after_feat: np.ndarray) -> np.ndarray:
    """
    Swappable change detection head.
    Computes per-patch L2 feature distance, min-max normalized to 0..1.
    """
    diff = np.linalg.norm(before_feat - after_feat, axis=-1)
    lo, hi = diff.min(), diff.max()
    if hi - lo < 1e-8:
        return np.zeros_like(diff)
    return (diff - lo) / (hi - lo)


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
    tolerance_deg: float = 0.05,
    min_quality: float = 0.25,
) -> List[Dict[str, Any]]:
    """
    Find usable observations for an AOI strictly within [date_from, date_to].
    Filters out observations with low quality or missing timestamps.
    """
    dt_from = _parse_date(date_from)
    dt_to = _parse_date(date_to)

    # If date_to was just a date (YYYY-MM-DD), make it inclusive to the end of that day
    if dt_to and len(str(date_to)) == 10:
        dt_to = dt_to.replace(hour=23, minute=59, second=59)

    with get_session() as session:
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

            candidates.append({
                "tile_id": t.tile_id,
                "scene_id": t.scene_id,
                "lon": t.lon,
                "lat": t.lat,
                "acquisition_date": t.acquisition_date,
                "tile_path": t.tile_path,
                "cloud_fraction": c_frac,
                "quality_score": q,
                "sensor": t.sensor,
            })

        # Sort chronologically
        candidates.sort(key=lambda c: c["acquisition_date"])
        return candidates


def run_change_detection(
    lon: float,
    lat: float,
    date_from: str,
    date_to: str,
) -> dict:
    candidates = find_candidate_tiles(lon, lat, date_from, date_to)
    if len(candidates) < 2:
        return {
            "status": "insufficient_data",
            "message": (
                f"Found {len(candidates)} usable observation(s) in the window {date_from} to {date_to}. "
                "Change detection requires at least 2 usable observations."
            ),
            "candidate_count": len(candidates),
            "earliest_supported_observation": candidates[0]["acquisition_date"].isoformat() if candidates else None,
        }

    before_cand, after_cand = candidates[0], candidates[-1]

    with get_session() as session:
        before_tile = session.get(Tile, before_cand["tile_id"])
        after_tile = session.get(Tile, after_cand["tile_id"])

        # 1. Load multi-spectral / RGB data
        before_raster, before_bmap = _load_tile_multispectral_or_rgb(before_tile)
        after_raster, after_bmap = _load_tile_multispectral_or_rgb(after_tile)

        # 2. Co-registration: Align after image to before image coordinate frame
        reg_result = register_image_pair(before_raster, after_raster)
        aligned_after_raster = reg_result.aligned_after

        # 3. Relative Radiometric Normalization: match after histogram to before
        norm_after_raster = normalize_histogram_match(aligned_after_raster, before_raster)

        # 4. Feature Extraction & Change Probability Map
        before_chw = np.transpose(before_raster[..., :3], (2, 0, 1))
        norm_after_chw = np.transpose(norm_after_raster[..., :3], (2, 0, 1))

        before_feat_map = prithvi_service.extract(before_chw)
        after_feat_map = prithvi_service.extract(norm_after_chw)

        change_prob_map = _difference_to_change_map(before_feat_map.array, after_feat_map.array)
        raw_change_score = float(change_prob_map.mean())

        # Resize probability map to full tile resolution
        h_orig, w_orig = before_tile.tile_size, before_tile.tile_size
        prob_map_full = cv2.resize(change_prob_map, (w_orig, h_orig), interpolation=cv2.INTER_LINEAR)
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

        # 6. Multi-Temporal Stack Evaluation (Earliest Supported Observation)
        temporal_scores = []
        earliest_change_date = after_tile.acquisition_date

        if len(candidates) > 2:
            for mid_cand in candidates[1:]:
                mid_t = session.get(Tile, mid_cand["tile_id"])
                mid_rast, _ = _load_tile_multispectral_or_rgb(mid_t)
                mid_chw = np.transpose(mid_rast[..., :3], (2, 0, 1))
                mid_feat = prithvi_service.extract(mid_chw)
                score_mid = float(_difference_to_change_map(before_feat_map.array, mid_feat.array).mean())
                temporal_scores.append(score_mid)
                if score_mid > settings.CHANGE_PROB_THRESHOLD and mid_t.acquisition_date < earliest_change_date:
                    earliest_change_date = mid_t.acquisition_date

        # 7. False-Alarm Suppression
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

        # Aggregate detected change types
        type_counts = {}
        for r in classified_regions:
            type_counts[r.change_type] = type_counts.get(r.change_type, 0) + r.area_pixels
        dominant_change_type = max(type_counts, key=type_counts.get) if type_counts else "no_significant_change"

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
            "change_id": result.change_id,
            "dominant_change_type": dominant_change_type,
            "change_score": suppression.change_score,
            "quality_score": suppression.quality_score,
            "confidence": suppression.confidence,
            "change_area_m2": round(total_change_area_m2, 1),
            "change_area_hectares": round(total_change_area_m2 / 10000.0, 2),
            "change_summary": f"{round(total_change_area_m2 / 10000.0, 1)} hectares of {dominant_change_type.replace('_', ' ')} detected with {int(suppression.confidence * 100)}% confidence.",
            "change_mask_path": str(mask_path),
            "change_mask_url": f"/static/tiles/change_masks/{mask_filename}",
            "earliest_supported_observation": earliest_change_date.isoformat(),
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
