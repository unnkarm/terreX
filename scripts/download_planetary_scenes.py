"""
Download real Sentinel-2 Level-2A Cloud-Optimized GeoTIFF (COG) imagery
from Microsoft Planetary Computer STAC API directly into data/incoming/.

Uses streaming windowed reads via HTTP range requests so only the specified AOI/patch
is fetched (takes seconds and uses minimal bandwidth).

Usage:
    python scripts/download_planetary_scenes.py
    python scripts/download_planetary_scenes.py --bbox 77.18 28.52 77.32 28.66 --count 2
    python scripts/download_planetary_scenes.py --dates 2023-01-01 2024-06-01
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from rasterio.enums import Resampling
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("terrex.planetary_downloader")

STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_SIGN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"

# Sentinel-2 bands to extract (10m & 20m resampled to 10m).  The first six
# map to Prithvi's HLS inputs; SCL is retained separately for cloud masking.
TARGET_BANDS = [
    ("B02", "blue"),
    ("B03", "green"),
    ("B04", "red"),
    ("B08", "nir"),
    ("B11", "swir1"),
    ("B12", "swir2"),
    ("SCL", "scl"),
]


def sign_url(url: str) -> str:
    """Signs a Planetary Computer blob URL using their anonymous SAS signing endpoint."""
    res = requests.get(SAS_SIGN_URL, params={"href": url}, timeout=15)
    res.raise_for_status()
    return res.json()["href"]


def search_sentinel_scenes(
    bbox: List[float],
    date_range: str,
    max_cloud_cover: float = 15.0,
    limit: int = 1,
    tile: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search for Sentinel-2 L2A STAC items."""

    query = {
        "eo:cloud_cover": {"lt": max_cloud_cover}
    }

    # Keep the same Sentinel-2 MGRS tile for all years
    if tile:
        query["s2:mgrs_tile"] = {"eq": tile}

    payload = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "datetime": date_range,
        "query": query,
        "limit": 20,
        "sortby": [
            {"field": "properties.datetime", "direction": "desc"}
        ],
    }

    logger.info(
        "Searching Planetary Computer STAC for Sentinel-2 scenes in %s...",
        date_range
    )

    res = requests.post(
        STAC_SEARCH_URL,
        json=payload,
        timeout=30
    )
    res.raise_for_status()

    features = res.json().get("features", [])

    logger.info(
        "Found %d candidate scene(s).",
        len(features)
    )

    return features[:limit]


def fetch_and_save_geotiff(
    item: Dict[str, Any],
    bbox_wgs84: List[float],
    output_path: Path,
    max_dim: int = 1024,
) -> Path:
    """
    Extracts multi-band AOI from remote COG assets and writes a local 6-band GeoTIFF.
    """
    item_id = item["id"]
    props = item.get("properties", {})
    acq_date_str = props.get("datetime", "")
    acq_date = acq_date_str[:10].replace("-", "") if acq_date_str else "unknown"
    assets = item.get("assets", {})

    logger.info("Processing scene %s (Acquired: %s)...", item_id, acq_date_str)

    # 1. Sign URL for reference band (B04 - 10m Red)
    if "B04" not in assets:
        raise ValueError(f"Scene {item_id} missing B04 asset")
    
    b04_signed = sign_url(assets["B04"]["href"])

    with rasterio.open(b04_signed) as ref_src:
        ref_crs = ref_src.crs
        # Transform WGS84 bbox [min_lon, min_lat, max_lon, max_lat] to scene native CRS
        min_x, min_y, max_x, max_y = transform_bounds(
            "EPSG:4326", ref_crs, *bbox_wgs84
        )
        
        # Calculate window from native bounds
        window = from_bounds(min_x, min_y, max_x, max_y, ref_src.transform)
        # Round and clamp window
        col_off = max(0, int(window.col_off))
        row_off = max(0, int(window.row_off))
        width = min(max_dim, int(window.width), ref_src.width - col_off)
        height = min(max_dim, int(window.height), ref_src.height - row_off)

        # Fallback if window is too small
        if width < 64 or height < 64:
            width = min(512, ref_src.width)
            height = min(512, ref_src.height)
            col_off = (ref_src.width - width) // 2
            row_off = (ref_src.height - height) // 2

        actual_win = rasterio.windows.Window(col_off, row_off, width, height)
        out_transform = rasterio.windows.transform(actual_win, ref_src.transform)

        logger.info(
            "Extracting window (%d, %d, %d, %d) from native %s at 10m GSD...",
            col_off, row_off, width, height, ref_crs
        )

        bands_data = []
        band_names = []

        for asset_key, band_name in TARGET_BANDS:
            if asset_key not in assets:
                logger.warning("Asset %s missing, filling with zeros.", asset_key)
                bands_data.append(np.zeros((height, width), dtype=np.uint16))
                band_names.append(band_name)
                continue

            asset_signed = sign_url(assets[asset_key]["href"])
            with rasterio.open(asset_signed) as src:
                # Read data into the exact (height, width) shape (handles 20m res bands via bilinear resampling)
                band_arr = src.read(
                    1,
                    window=from_bounds(*rasterio.windows.bounds(actual_win, ref_src.transform), src.transform),
                    out_shape=(height, width),
                    resampling=Resampling.bilinear if band_name != "scl" else Resampling.nearest,
                )
                bands_data.append(band_arr.astype(np.uint16))
                band_names.append(band_name)

        stack = np.stack(bands_data, axis=0)  # (6, H, W)

        # Write output GeoTIFF
        output_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": len(TARGET_BANDS),
            "dtype": np.uint16,
            "crs": ref_crs,
            "transform": out_transform,
            "compress": "deflate",
        }

        with rasterio.open(output_path, "w", **meta) as dst:
            dst.write(stack)
            dst.update_tags(
                SENSOR="Sentinel-2",
                BAND_NAMES=",".join(band_names),
                ACQUISITION_DATE=acq_date_str,
                STAC_ITEM_ID=item_id,
                PLATFORM="PlanetaryComputer",
            )
            for idx, (_, bname) in enumerate(TARGET_BANDS, start=1):
                dst.set_band_description(idx, bname)

    logger.info("Successfully saved real Sentinel-2 GeoTIFF to %s (size: %dx%d)", output_path, width, height)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Download real Sentinel-2 GeoTIFFs from Planetary Computer.")
    parser.add_argument(
        "--preset",
        choices=["kolkata"],
        default="kolkata",
        help="Predefined geographic AOI (default: kolkata)",
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        default=None,
        help="AOI bounding box: min_lon min_lat max_lon max_lat (overrides preset)",
    )
    parser.add_argument(
        "--dates",
        nargs=2,
        default=None,
        help="Start and end date in YYYY-MM-DD format (overrides preset)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=4,
        help="Number of multi-temporal scenes to fetch across years (default: 4)",
    )
    parser.add_argument(
        "--max-cloud",
        type=float,
        default=15.0,
        help="Maximum cloud cover percentage (default: 15%%)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Destination directory (default: data/sentinel2/<preset>/ and data/incoming/)",
    )
    parser.add_argument(
        "--max-dim",
        type=int,
        default=512,
        help="Maximum pixel dimension per tile (e.g. 512, 1024)",
    )

    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be at least 1")

    # Apply presets
    PRESETS = {
        "kolkata": {
            "bbox": [88.25, 22.45, 88.48, 22.65],  # Hooghly river & urban expansion (~35 km²)
            "dates": ["2023-01-01", "2026-09-04"],
        },
    }

    selected_bbox = args.bbox or PRESETS[args.preset]["bbox"]
    operational_bounds = [87.75, 21.40, 88.65, 23.60]
    if not (
        operational_bounds[0] <= selected_bbox[0] < selected_bbox[2] <= operational_bounds[2]
        and operational_bounds[1] <= selected_bbox[1] < selected_bbox[3] <= operational_bounds[3]
    ):
        parser.error(f"AOI must stay inside {operational_bounds}; max longitude is 88.65E")
    selected_dates = args.dates or PRESETS[args.preset]["dates"]
    out_dir = args.out_dir or (Path(__file__).resolve().parent.parent / "data" / "incoming")
    out_dir.mkdir(parents=True, exist_ok=True)

    date_str = f"{selected_dates[0]}/{selected_dates[1]}"
    logger.info("Operating with preset '%s': BBox=%s, Window=%s", args.preset, selected_bbox, date_str)

    # Fetch at most one scene per calendar year.  The first result establishes
    # the MGRS tile; all later searches are constrained to that tile so the
    # resulting time series covers the same ground.
    start = datetime.fromisoformat(selected_dates[0]).date()
    end = datetime.fromisoformat(selected_dates[1]).date()
    if end < start:
        parser.error("--dates end date must not be earlier than the start date")

    items = []
    target_tile = None
    years = range(start.year, end.year + 1)

    for year in years:
        if len(items) >= args.count:
            break

        range_start = max(start, datetime(year, 1, 1).date())
        range_end = min(end, datetime(year, 12, 31).date())
        year_range = f"{range_start.isoformat()}/{range_end.isoformat()}"

        year_items = search_sentinel_scenes(
            bbox=selected_bbox,
            date_range=year_range,
            max_cloud_cover=args.max_cloud,
            limit=1,
            tile=target_tile,
        )

        if year_items:
            item = year_items[0]
            items.append(item)
            target_tile = target_tile or item.get("properties", {}).get("s2:mgrs_tile")
            logger.info(
                "Selected %s scene: %s (MGRS tile: %s)",
                year,
                item["id"],
                target_tile or "unconstrained",
            )
        else:
            logger.warning(
                "No suitable Sentinel-2 scene found for %s.",
                year
            )

    if not items:
        logger.error("No low-cloud Sentinel-2 scenes found for the specified criteria.")
        return

    for idx, item in enumerate(items, start=1):
        dt_raw = item.get("properties", {}).get("datetime", f"scene_{idx}")
        clean_date = dt_raw[:10].replace("-", "")
        tile_name = f"Sentinel-2_{clean_date}_Planetary_{item['id'][:12]}.tif"
        out_file = out_dir / tile_name
        try:
            fetch_and_save_geotiff(item, selected_bbox, out_file, max_dim=args.max_dim)
        except Exception as err:
            logger.exception("Failed to fetch scene %s: %s", item["id"], err)


if __name__ == "__main__":
    main()
