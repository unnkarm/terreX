from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Optional

from services.change_detection import run_change_detection

router = APIRouter(prefix="/api/change", tags=["change-detection"])


@router.get("/detect")
def detect_change(
    lon: float = Query(...),
    lat: float = Query(...),
    date_from: str = Query(...),
    date_to: str = Query(...),
):
    """
    Feature 4 + 5: run change detection for an AOI (point + implicit tile
    radius) and date range, with false-alarm suppression applied and full
    provenance/confidence returned.
    """
    return run_change_detection(lon=lon, lat=lat, date_from=date_from, date_to=date_to)
