"""
TerreX Offline Basemap Tile Service.

Serves pre-cached and on-demand satellite XYZ raster tiles (data/offline_basemap/tiles/{z}/{x}/{y}.png).
Enables 100% air-gapped, offline satellite map visualization in MapLibre.
"""
from __future__ import annotations

import io
import os
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Response, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw

from config import settings

logger = logging.getLogger("terrex.basemap")
router = APIRouter(prefix="/api/basemap", tags=["basemap"])

BASEMAP_TILES_DIR = settings.DATA_DIR / "offline_basemap" / "tiles"
BASEMAP_TILES_DIR.mkdir(parents=True, exist_ok=True)

# Upstream satellite tile server for pre-caching
UPSTREAM_SATELLITE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)

# 256x256 fallback dark tactical tile for uncached offline coordinates
_FALLBACK_TILE_BYTES: Optional[bytes] = None


def _get_fallback_tile() -> bytes:
    global _FALLBACK_TILE_BYTES
    if _FALLBACK_TILE_BYTES is None:
        img = Image.new("RGBA", (256, 256), color=(8, 12, 20, 255))
        draw = ImageDraw.Draw(img)
        # Subtle grid borders
        draw.rectangle([0, 0, 255, 255], outline=(20, 35, 55, 120), width=1)
        # Center reticle mark
        draw.line([124, 128, 132, 128], fill=(30, 60, 90, 160), width=1)
        draw.line([128, 124, 128, 132], fill=(30, 60, 90, 160), width=1)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        _FALLBACK_TILE_BYTES = buf.getvalue()
    return _FALLBACK_TILE_BYTES


@router.get("/tiles/{z}/{x}/{y}.png")
async def get_basemap_tile(z: int, x: int, y: int):
    """
    Serve a satellite XYZ raster tile from local offline disk storage.
    If uncached and network is available, downloads and caches the tile atomically.
    """
    tile_file = BASEMAP_TILES_DIR / str(z) / str(x) / f"{y}.png"

    # 1. Local Cache Hit (0ms local disk read)
    if tile_file.exists() and tile_file.stat().st_size > 0:
        return FileResponse(
            tile_file,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "X-TerreX-Tile-Source": "offline-cache",
            },
        )

    # 2. Acquisition-time convenience only. Operational OFFLINE_MODE never
    # attempts an outbound request for a cache miss.
    if not settings.OFFLINE_MODE:
      try:
          import urllib.request
          url = UPSTREAM_SATELLITE_URL.format(z=z, y=y, x=x)
          req = urllib.request.Request(
              url,
              headers={"User-Agent": "TerreX-Offline-Basemap-Cache/1.0"},
          )
          with urllib.request.urlopen(req, timeout=3.0) as resp:
              if resp.status == 200:
                  data = resp.read()
                  if len(data) > 200:  # valid image payload
                      tile_file.parent.mkdir(parents=True, exist_ok=True)
                      temp_file = tile_file.with_suffix(".tmp")
                      temp_file.write_bytes(data)
                      temp_file.replace(tile_file)
                      return Response(
                          content=data,
                          media_type="image/png",
                          headers={
                              "Cache-Control": "public, max-age=31536000, immutable",
                              "X-TerreX-Tile-Source": "upstream-cached",
                          },
                      )
      except Exception:
          pass

    # 3. Offline Fallback (returns dark tactical grid tile so MapLibre canvas remains unbroken)
    return Response(
        content=_get_fallback_tile(),
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-TerreX-Tile-Source": "offline-fallback",
        },
    )


@router.get("/status")
def get_basemap_cache_status():
    """Return disk usage and tile count of the offline satellite tile cache."""
    total_size = 0
    tile_count = 0
    zoom_levels = set()

    if BASEMAP_TILES_DIR.exists():
        for root, _, files in os.walk(BASEMAP_TILES_DIR):
            for f in files:
                if f.endswith(".png"):
                    tile_count += 1
                    p = Path(root) / f
                    total_size += p.stat().st_size
                    # Zoom level is first subfolder under tiles/
                    try:
                        rel = p.relative_to(BASEMAP_TILES_DIR)
                        zoom_levels.add(int(rel.parts[0]))
                    except Exception:
                        pass

    return {
        "status": "active",
        "cached_tiles": tile_count,
        "size_mb": round(total_size / (1024 * 1024), 2),
        "zoom_levels": sorted(list(zoom_levels)),
        "cache_directory": str(BASEMAP_TILES_DIR),
        "offline_ready": tile_count > 0,
        "outbound_fetch_enabled": not settings.OFFLINE_MODE,
    }
