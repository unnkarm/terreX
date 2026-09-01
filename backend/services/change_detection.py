"""
Feature 4 — Change detection.

AOI + start date + end date -> pick nearest usable before/after tiles ->
Prithvi (or placeholder statistical) features for each -> feature
difference -> change probability map -> Feature 5 suppression -> stored
ChangeResult with full provenance.

"Change detection head": for the MVP this is a simple, documented
feature-difference + threshold approach (per the spec's explicit fallback
instruction), implemented as a tiny, swappable function
(`_difference_to_change_map`) so a trained head can replace it later
without touching the rest of the pipeline.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from sqlalchemy import select, and_

from config import settings
from db.database import get_session
from db.models import Tile, ChangeResult
from services.prithvi import prithvi_service
from services.quality import (
    cloud_fraction_estimate, valid_pixel_fraction, sharpness_score,
    overall_quality_score, registration_offset_estimate,
)
from services.false_alarm import evaluate, ObservationQuality


def _load_tile_image_chw(tile: Tile) -> np.ndarray:
    img = Image.open(tile.tile_path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return np.transpose(arr, (2, 0, 1))  # CHW


def _difference_to_change_map(before_feat: np.ndarray, after_feat: np.ndarray) -> np.ndarray:
    """
    Swappable "change detection head". MVP implementation: per-patch L2
    feature distance, min-max normalised to a 0..1 probability-like map.
    Replace with a trained head's forward pass when available — signature
    stays (before_features, after_features) -> HxW probability map.
    """
    diff = np.linalg.norm(before_feat - after_feat, axis=-1)
    lo, hi = diff.min(), diff.max()
    if hi - lo < 1e-8:
        return np.zeros_like(diff)
    return (diff - lo) / (hi - lo)


def find_candidate_tiles(lon: float, lat: float, date_from: str, date_to: str, tolerance_deg: float = 0.01):
    """Find the nearest-in-time usable tile at/near this location for each end of the range."""
    with get_session() as session:
        rows = session.execute(
            select(Tile).where(
                and_(
                    Tile.lon.between(lon - tolerance_deg, lon + tolerance_deg),
                    Tile.lat.between(lat - tolerance_deg, lat + tolerance_deg),
                )
            )
        ).scalars().all()
        # detach usable fields before session closes
        return [
            {
                "tile_id": t.tile_id, "lon": t.lon, "lat": t.lat,
                "acquisition_date": t.acquisition_date, "tile_path": t.tile_path,
                "cloud_fraction": t.cloud_fraction, "quality_score": t.quality_score,
            }
            for t in rows
        ]


def run_change_detection(
    lon: float,
    lat: float,
    date_from: str,
    date_to: str,
    temporal_series_dates: Optional[list] = None,
) -> dict:
    candidates = find_candidate_tiles(lon, lat, date_from, date_to)
    if len(candidates) < 2:
        return {
            "status": "insufficient_data",
            "message": (
                "Fewer than 2 usable observations found for this AOI/date range. "
                "Change detection requires at least a before and an after tile."
            ),
            "earliest_supported_observation": min(
                (c["acquisition_date"] for c in candidates if c["acquisition_date"]), default=None
            ),
        }

    dated = [c for c in candidates if c["acquisition_date"]]
    dated.sort(key=lambda c: c["acquisition_date"])
    before, after = dated[0], dated[-1]

    with get_session() as session:
        before_tile = session.get(Tile, before["tile_id"])
        after_tile = session.get(Tile, after["tile_id"])

        before_chw = _load_tile_image_chw(before_tile)
        after_chw = _load_tile_image_chw(after_tile)

        before_feat_map = prithvi_service.extract(before_chw)
        after_feat_map = prithvi_service.extract(after_chw)

        change_prob_map = _difference_to_change_map(before_feat_map.array, after_feat_map.array)
        raw_change_score = float(change_prob_map.mean())

        before_rgb = np.transpose(before_chw, (1, 2, 0))
        after_rgb = np.transpose(after_chw, (1, 2, 0))
        before_q = ObservationQuality(
            cloud_fraction=cloud_fraction_estimate(before_rgb),
            valid_pixel_fraction=valid_pixel_fraction(before_chw),
            sharpness=sharpness_score(before_rgb.mean(axis=-1)),
            quality_score=before_tile.quality_score or 0.5,
        )
        after_q = ObservationQuality(
            cloud_fraction=cloud_fraction_estimate(after_rgb),
            valid_pixel_fraction=valid_pixel_fraction(after_chw),
            sharpness=sharpness_score(after_rgb.mean(axis=-1)),
            quality_score=after_tile.quality_score or 0.5,
        )

        dx, dy, corr = registration_offset_estimate(before_rgb.mean(axis=-1), after_rgb.mean(axis=-1))
        radiometric_diff = float(abs(before_rgb.mean() - after_rgb.mean()))

        temporal_series = None
        if len(dated) > 2:
            temporal_series = []
            for mid in dated[1:-1]:
                mid_tile = session.get(Tile, mid["tile_id"])
                mid_chw = _load_tile_image_chw(mid_tile)
                mid_feat = prithvi_service.extract(mid_chw)
                temporal_series.append(float(_difference_to_change_map(before_feat_map.array, mid_feat.array).mean()))

        suppression = evaluate(
            raw_change_score=raw_change_score,
            before_q=before_q,
            after_q=after_q,
            registration_correlation=corr,
            radiometric_diff=radiometric_diff,
            temporal_series=temporal_series,
        )

        mask_dir = settings.TILES_DIR / "change_masks"
        mask_dir.mkdir(exist_ok=True)
        mask_path = mask_dir / f"{before_tile.tile_id}_{after_tile.tile_id}.png"
        mask_img = (np.clip(change_prob_map, 0, 1) * 255).astype(np.uint8)
        Image.fromarray(mask_img).resize(
            (before_tile.tile_size, before_tile.tile_size), Image.NEAREST
        ).save(mask_path)

        pixel_area_m2 = (before_tile.resolution_m or 10.0) ** 2
        changed_fraction = float((change_prob_map > settings.CHANGE_PROB_THRESHOLD).mean())
        change_area_m2 = changed_fraction * (before_tile.tile_size ** 2) * pixel_area_m2

        method = "feature-diff-placeholder" if before_feat_map.is_placeholder else "prithvi-diff"

        result = ChangeResult(
            before_tile_id=before_tile.tile_id,
            after_tile_id=after_tile.tile_id,
            change_score=suppression.change_score,
            quality_score=suppression.quality_score,
            confidence=suppression.confidence,
            change_area_m2=round(change_area_m2, 1),
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
            "before": {
                "tile_id": before_tile.tile_id,
                "acquisition_date": before_tile.acquisition_date.isoformat() if before_tile.acquisition_date else None,
                "thumbnail_path": before_tile.thumbnail_path,
                "quality": before_q.__dict__,
            },
            "after": {
                "tile_id": after_tile.tile_id,
                "acquisition_date": after_tile.acquisition_date.isoformat() if after_tile.acquisition_date else None,
                "thumbnail_path": after_tile.thumbnail_path,
                "quality": after_q.__dict__,
            },
            "change_score": suppression.change_score,
            "quality_score": suppression.quality_score,
            "confidence": suppression.confidence,
            "change_area_m2": round(change_area_m2, 1),
            "change_mask_path": str(mask_path),
            "reasons": suppression.reasons,
            "method": method,
            "is_placeholder_model": before_feat_map.is_placeholder,
            "registration_correlation": corr,
            "earliest_supported_observation": dated[0]["acquisition_date"].isoformat(),
        }
