from __future__ import annotations

from fastapi import APIRouter, Query, Body
from typing import Optional, List
from pydantic import BaseModel

from services.change_detection import run_change_detection

router = APIRouter(prefix="/api/change", tags=["change-detection"])


class ChangeDetectRequest(BaseModel):
    before_scene: Optional[str] = None
    after_scene: Optional[str] = None
    aoi: Optional[List[float]] = None  # [min_lon, min_lat, max_lon, max_lat] or [lon, lat]
    lon: Optional[float] = None
    lat: Optional[float] = None
    date_from: Optional[str] = "2023-01-01"
    date_to: Optional[str] = "2026-01-01"


@router.get("/detect")
def detect_change_get(
    lon: float = Query(...),
    lat: float = Query(...),
    date_from: str = Query(...),
    date_to: str = Query(...),
):
    """
    Run bi-temporal change detection for an AOI and date range.
    Returns co-registered change probability map, dominant change type,
    affected ground area in m2 and hectares, and explainable evidence checklist.
    """
    return run_change_detection(lon=lon, lat=lat, date_from=date_from, date_to=date_to)


@router.post("/detect")
def detect_change_post(payload: ChangeDetectRequest = Body(...)):
    """
    JSON POST endpoint for change detection.
    Accepts { before_scene, after_scene, aoi } or { lon, lat, date_from, date_to }.
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

    return run_change_detection(
        lon=target_lon,
        lat=target_lat,
        date_from=date_from,
        date_to=date_to,
    )
