from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Query
from PIL import Image

from services.search import semantic_text_search, image_to_image_search

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/text")
def search_text(
    q: str = Query(..., description="Natural language query, e.g. 'new buildings near a river'"),
    top_k: int = 20,
    sensor: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_similarity: float = 0.0,
    min_lon: Optional[float] = None,
    min_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
    max_lat: Optional[float] = None,
):
    aoi_bbox = None
    if None not in (min_lon, min_lat, max_lon, max_lat):
        aoi_bbox = (min_lon, min_lat, max_lon, max_lat)
    return semantic_text_search(
        query=q, top_k=top_k, sensor=sensor, date_from=date_from, date_to=date_to,
        min_similarity=min_similarity, aoi_bbox=aoi_bbox,
    )


@router.post("/image")
async def search_image(
    file: UploadFile = File(...),
    top_k: int = Form(20),
    sensor: Optional[str] = Form(None),
    date_from: Optional[str] = Form(None),
    date_to: Optional[str] = Form(None),
    min_similarity: float = Form(0.0),
):
    contents = await file.read()
    image = Image.open(io.BytesIO(contents))
    return image_to_image_search(
        image=image, top_k=top_k, sensor=sensor, date_from=date_from,
        date_to=date_to, min_similarity=min_similarity,
    )
