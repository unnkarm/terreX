"""
Unit tests for image decoding and image-to-image search error resilience.
"""
import io
import sys
from pathlib import Path

# Add backend to path for tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import numpy as np
import pytest
import rasterio
from rasterio.io import MemoryFile
from PIL import Image
from fastapi import HTTPException

from api.routes_search import decode_image_bytes


def test_decode_standard_png():
    img = Image.new("RGB", (100, 100), color=(255, 128, 64))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    decoded = decode_image_bytes(buf.getvalue())
    assert decoded.size == (100, 100)
    assert decoded.mode == "RGB"


def test_decode_standard_jpeg():
    img = Image.new("RGB", (64, 64), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    decoded = decode_image_bytes(buf.getvalue())
    assert decoded.size == (64, 64)
    assert decoded.mode == "RGB"


def test_decode_multiband_16bit_geotiff():
    # 4-band 16-bit GeoTIFF (e.g. Sentinel-2 / Landsat format)
    data = np.random.randint(200, 4000, (4, 128, 128), dtype=np.uint16)
    mem = MemoryFile()
    with mem.open(driver="GTiff", width=128, height=128, count=4, dtype=data.dtype) as src:
        src.write(data)
    raw_geotiff = bytes(mem.getbuffer())

    # PIL Image.open normally raises PIL.UnidentifiedImageError on this
    with pytest.raises(Exception):
        Image.open(io.BytesIO(raw_geotiff)).load()

    # Our decode_image_bytes successfully handles it via rasterio fallback
    decoded = decode_image_bytes(raw_geotiff)
    assert decoded.size == (128, 128)
    assert decoded.mode == "RGB"


def test_decode_single_band_geotiff():
    data = np.random.randint(0, 255, (1, 64, 64), dtype=np.uint8)
    mem = MemoryFile()
    with mem.open(driver="GTiff", width=64, height=64, count=1, dtype=data.dtype) as src:
        src.write(data)
    raw_geotiff = bytes(mem.getbuffer())

    decoded = decode_image_bytes(raw_geotiff)
    assert decoded.size == (64, 64)
    assert decoded.mode == "RGB"


def test_decode_empty_bytes_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        decode_image_bytes(b"")
    assert exc_info.value.status_code == 400
    assert "empty" in exc_info.value.detail.lower()


def test_decode_invalid_corrupted_file_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        decode_image_bytes(b"NOT_AN_IMAGE_CONTENT_XYZ")
    assert exc_info.value.status_code == 400
    assert "unable to identify or decode" in exc_info.value.detail.lower()
