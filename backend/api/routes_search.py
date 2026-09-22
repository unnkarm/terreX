from __future__ import annotations

import io
import logging
import json
from typing import Optional, Any, List, Dict
from pydantic import BaseModel
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException, Body
from PIL import Image

from config import settings
from services.search import semantic_text_search, image_to_image_search
from services.nlp_filter import parse_natural_language_query
from services.ranking import detect_temporal_query_intent

logger = logging.getLogger("terrex.api.search")
router = APIRouter(prefix="/api/search", tags=["search"])


def _operational_bbox(values) -> Optional[tuple[float, float, float, float]]:
    bounds = (
        settings.KOLKATA_AOI_MIN_LON,
        settings.KOLKATA_AOI_MIN_LAT,
        settings.KOLKATA_AOI_MAX_LON,
        settings.KOLKATA_AOI_MAX_LAT,
    )
    supplied = [value is not None for value in values]
    if any(supplied) and not all(supplied):
        raise HTTPException(status_code=422, detail="All four AOI bounds must be supplied together")
    if not any(supplied):
        return None
    min_lon, min_lat, max_lon, max_lat = (float(value) for value in values)
    if min_lon >= max_lon or min_lat >= max_lat:
        raise HTTPException(status_code=422, detail="AOI minimum bounds must be below maximum bounds")

    # Map-derived and scene-footprint AOIs may extend slightly beyond the
    # operational boundary. Intersect them instead of rejecting the search.
    clipped = (
        max(min_lon, bounds[0]),
        max(min_lat, bounds[1]),
        min(max_lon, bounds[2]),
        min(max_lat, bounds[3]),
    )
    if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
        raise HTTPException(
            status_code=422,
            detail=f"AOI does not intersect the Greater Kolkata / West Bengal operational bounds {bounds}",
        )
    return clipped


def _validate_operational_polygon(polygon: Any) -> None:
    if polygon is None:
        return
    coordinates = polygon.get("coordinates") if isinstance(polygon, dict) else polygon
    points: list[tuple[float, float]] = []

    def visit(value):
        if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            points.append((float(value[0]), float(value[1])))
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(coordinates)
    if not points:
        raise HTTPException(status_code=422, detail="AOI polygon contains no valid coordinates")
    bounds = (
        settings.KOLKATA_AOI_MIN_LON,
        settings.KOLKATA_AOI_MIN_LAT,
        settings.KOLKATA_AOI_MAX_LON,
        settings.KOLKATA_AOI_MAX_LAT,
    )
    if any(not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]) for lon, lat in points):
        raise HTTPException(status_code=422, detail=f"AOI polygon must stay inside operational bounds {bounds}")


class TextSearchRequest(BaseModel):
    query: str
    top_k: int = 20
    sensor: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    min_similarity: float = 0.0
    min_lon: Optional[float] = None
    min_lat: Optional[float] = None
    max_lon: Optional[float] = None
    max_lat: Optional[float] = None
    aoi_polygon: Optional[Any] = None


@router.get("/parse-query")
def parse_query_endpoint(q: str = Query(..., description="Query to parse into structured filters")):
    """Tier 1.2 NL filter parse endpoint."""
    parsed = parse_natural_language_query(q)
    temporal_query, temporal_keywords = detect_temporal_query_intent(q)
    return {
        "raw_query": parsed.raw_query,
        "semantic_query": parsed.semantic_query,
        "spatial_relation": {
            "type": parsed.spatial_relation.relation_type,
            "target": parsed.spatial_relation.target,
            "distance_km": parsed.spatial_relation.distance_km,
            "resolved_name": parsed.spatial_relation.resolved_feature_name,
        } if parsed.spatial_relation else None,
        "date_from": parsed.date_from,
        "date_to": parsed.date_to,
        "max_cloud_cover": parsed.max_cloud_cover,
        "sensor": parsed.sensor,
        "explanation": parsed.explanation,
        "temporal_change_intent": temporal_query,
        "temporal_keywords": temporal_keywords,
    }


def decode_image_bytes(contents: bytes) -> Image.Image:
    """
    Robustly decodes uploaded image bytes into a PIL RGB Image.
    Supports standard formats (JPEG, PNG, WebP, BMP) and multi-band / 16-bit GeoTIFFs / COGs.
    """
    if not contents or len(contents) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded image file is empty. Please select a valid image file.",
        )

    # 1. Attempt standard PIL Image decoding
    try:
        image = Image.open(io.BytesIO(contents))
        image.load()
        if image.mode != "RGB":
            image = image.convert("RGB")
        return image
    except Exception as pil_err:
        logger.debug(
            "Standard PIL decoding failed (%s), attempting rasterio geospatial decoder...",
            pil_err,
        )

    # 2. Attempt rasterio decoding (handles GeoTIFF, COG, 16-bit, multi-band)
    try:
        import rasterio
        from rasterio.io import MemoryFile

        with MemoryFile(contents) as memfile:
            with memfile.open() as src:
                if src.count >= 3:
                    arr = src.read([1, 2, 3])
                elif src.count == 1:
                    band = src.read(1)
                    arr = np.stack([band, band, band], axis=0)
                elif src.count == 2:
                    b1 = src.read(1)
                    b2 = src.read(2)
                    arr = np.stack([b1, b2, b1], axis=0)
                else:
                    arr = src.read()
                    if arr.shape[0] < 3:
                        arr = np.repeat(arr[:1], 3, axis=0)
                    else:
                        arr = arr[:3]

                # Convert to float and apply standard 2%-98% percentile stretch for display/embedding
                arr = arr.astype(np.float32)
                arr = np.nan_to_num(arr, nan=0.0, posinf=255.0, neginf=0.0)
                p2, p98 = np.percentile(arr, (2, 98))
                if p98 > p2:
                    arr = (arr - p2) / (p98 - p2) * 255.0
                else:
                    min_v, max_v = arr.min(), arr.max()
                    if max_v > min_v:
                        arr = (arr - min_v) / (max_v - min_v) * 255.0
                    else:
                        arr = np.zeros_like(arr)

                arr = np.clip(arr, 0, 255).astype(np.uint8)
                arr_rgb = np.transpose(arr, (1, 2, 0))
                return Image.fromarray(arr_rgb, mode="RGB")
    except Exception as rio_err:
        logger.warning("Rasterio decoding also failed: %s", rio_err)

    raise HTTPException(
        status_code=400,
        detail="Unable to identify or decode image file. Please upload a valid image (PNG, JPEG, TIFF/GeoTIFF, WebP).",
    )


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
    polygon: Optional[str] = Query(None, description="GeoJSON polygon or coordinates JSON"),
):
    aoi_bbox = _operational_bbox((min_lon, min_lat, max_lon, max_lat))
    
    aoi_poly = None
    if polygon:
        try:
            aoi_poly = json.loads(polygon)
        except Exception:
            raise HTTPException(status_code=422, detail="polygon must be valid JSON")
    _validate_operational_polygon(aoi_poly)

    if sensor and sensor.lower().strip() in ("all", "all sensors", "all_sensors", "", "none"):
        sensor = None

    return semantic_text_search(
        query=q, top_k=top_k, sensor=sensor, date_from=date_from, date_to=date_to,
        min_similarity=min_similarity, aoi_bbox=aoi_bbox, aoi_polygon=aoi_poly,
    )


@router.post("/text")
def search_text_post(req: TextSearchRequest = Body(...)):
    """POST JSON endpoint for text search with arbitrary GeoJSON polygon filter."""
    aoi_bbox = _operational_bbox((req.min_lon, req.min_lat, req.max_lon, req.max_lat))
    _validate_operational_polygon(req.aoi_polygon)

    sensor = req.sensor
    if sensor and sensor.lower().strip() in ("all", "all sensors", "all_sensors", "", "none"):
        sensor = None

    return semantic_text_search(
        query=req.query,
        top_k=req.top_k,
        sensor=sensor,
        date_from=req.date_from,
        date_to=req.date_to,
        min_similarity=req.min_similarity,
        aoi_bbox=aoi_bbox,
        aoi_polygon=req.aoi_polygon,
    )


@router.post("/image")
async def search_image(
    file: UploadFile = File(...),
    top_k: int = Form(20),
    sensor: Optional[str] = Form(None),
    date_from: Optional[str] = Form(None),
    date_to: Optional[str] = Form(None),
    min_similarity: float = Form(0.0),
    min_lon: Optional[float] = Form(None),
    min_lat: Optional[float] = Form(None),
    max_lon: Optional[float] = Form(None),
    max_lat: Optional[float] = Form(None),
    polygon: Optional[str] = Form(None),
):
    try:
        contents = await file.read()
        image = decode_image_bytes(contents)
        
        aoi_bbox = _operational_bbox((min_lon, min_lat, max_lon, max_lat))

        aoi_poly = None
        if polygon:
            try:
                aoi_poly = json.loads(polygon)
            except Exception:
                raise HTTPException(status_code=422, detail="polygon must be valid JSON")
        _validate_operational_polygon(aoi_poly)

        if sensor and sensor.lower().strip() in ("all", "all sensors", "all_sensors", "", "none"):
            sensor = None

        return image_to_image_search(
            image=image, top_k=top_k, sensor=sensor, date_from=date_from,
            date_to=date_to, min_similarity=min_similarity, aoi_bbox=aoi_bbox, aoi_polygon=aoi_poly,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error during image search: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Image search failed: {str(exc)}",
        )
