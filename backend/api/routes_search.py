from __future__ import annotations

import io
import logging
from typing import Optional

import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException
from PIL import Image

from services.search import semantic_text_search, image_to_image_search

logger = logging.getLogger("terrex.api.search")
router = APIRouter(prefix="/api/search", tags=["search"])


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
    try:
        contents = await file.read()
        image = decode_image_bytes(contents)
        return image_to_image_search(
            image=image, top_k=top_k, sensor=sensor, date_from=date_from,
            date_to=date_to, min_similarity=min_similarity,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error during image search: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Image search failed: {str(exc)}",
        )
