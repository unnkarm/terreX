from __future__ import annotations

from fastapi import APIRouter, Query, Body, HTTPException
from typing import Optional, List
from pydantic import BaseModel

from services.dense_change_detection import run_dense_change_detection
from services.change_detection import list_available_acquisitions

router = APIRouter(prefix="/api/change", tags=["change-detection"])


class ChangeDetectRequest(BaseModel):
    before_scene: Optional[str] = None
    after_scene: Optional[str] = None
    aoi: Optional[List[float]] = None  # [min_lon, min_lat, max_lon, max_lat] or [lon, lat]
    lon: Optional[float] = None
    lat: Optional[float] = None
    tile_id: Optional[str] = None
    date_from: Optional[str] = "2023-01-01"
    date_to: Optional[str] = "2026-01-01"
    baseline_n: int = 3
    persistence_k: int = 2
    threshold: Optional[float] = None
    change_prob_threshold: Optional[float] = None
    change_map_threshold: Optional[float] = None


@router.get("/acquisitions")
def available_acquisitions(
    lon: float = Query(...),
    lat: float = Query(...),
    tile_id: Optional[str] = Query(None),
):
    """List actual AOI acquisition timestamps for date controls and scrubbing."""
    observations = list_available_acquisitions(lon, lat, reference_tile_id=tile_id)
    return {
        "count": len(observations),
        "available_dates": [item["date_formatted"] for item in observations],
        "observations": observations,
    }


@router.get("/detect")
def detect_change_get(
    lon: float = Query(...),
    lat: float = Query(...),
    date_from: str = Query(...),
    date_to: str = Query(...),
    tile_id: Optional[str] = Query(None),
    baseline_n: int = Query(3, ge=1, le=10),
    persistence_k: int = Query(2, ge=2, le=5),
    threshold: Optional[float] = Query(None, gt=0.0, le=1.0),
    change_prob_threshold: Optional[float] = Query(None, gt=0.0, le=1.0),
    change_map_threshold: Optional[float] = Query(None, gt=0.0, le=1.0),
):
    """
    Run dense multi-temporal change-point detection for an AOI and date range.
    Optical and SAR passes are normalized against modality-specific rolling
    baselines before the interleaved persistence rule is evaluated.
    """
    try:
        return run_dense_change_detection(
            lon=lon, lat=lat, date_from=date_from, date_to=date_to, tile_id=tile_id,
            baseline_n=baseline_n, persistence_k=persistence_k, threshold=threshold,
            change_prob_threshold=change_prob_threshold,
            change_map_threshold=change_map_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/detect")
def detect_change_post(payload: ChangeDetectRequest = Body(...)):
    """
    JSON POST endpoint for change detection.
    Accepts { before_scene, after_scene, aoi } or { lon, lat, date_from, date_to, tile_id }.
    """
    target_lon = payload.lon
    target_lat = payload.lat

    if (target_lon is None or target_lat is None) and payload.aoi:
        if len(payload.aoi) == 4:
            target_lon = (payload.aoi[0] + payload.aoi[2]) / 2.0
            target_lat = (payload.aoi[1] + payload.aoi[3]) / 2.0
        elif len(payload.aoi) >= 2:
            target_lon = payload.aoi[0]
            target_lat = payload.aoi[1]

    # Default to center of Kolkata if coordinates not provided
    if target_lon is None:
        target_lon = 88.3639
    if target_lat is None:
        target_lat = 22.5726

    date_from = payload.date_from or "2023-01-01"
    date_to = payload.date_to or "2026-01-01"

    try:
        return run_dense_change_detection(
            lon=target_lon,
            lat=target_lat,
            date_from=date_from,
            date_to=date_to,
            tile_id=payload.tile_id,
            baseline_n=payload.baseline_n,
            persistence_k=payload.persistence_k,
            threshold=payload.threshold,
            change_prob_threshold=payload.change_prob_threshold,
            change_map_threshold=payload.change_map_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
