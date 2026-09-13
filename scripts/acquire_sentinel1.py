"""
Acquire Sentinel-1 GRD SAR imagery for the TerreX demo AOI via the
Copernicus Data Space Ecosystem OData API.

Target: ≥ 1 scene overlapping a known-cloudy Sentinel-2 date window so the
"All-Weather Cloud Penetrator" demo (TerreX demo scenario #6) can show
radar backscatter when optical fails.

Usage:
  python scripts/acquire_sentinel1.py

Required env vars: same as acquire_sentinel2.py
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from acquisition_common import acquire_from_copernicus, DEFAULT_BBOX, resolve_bbox
except ImportError:
    from scripts.acquisition_common import acquire_from_copernicus, DEFAULT_BBOX, resolve_bbox  # type: ignore

# Monsoon window — highest cloud probability over Kolkata; radar is most useful here
_SENTINEL1_DATE_RANGES: List[tuple] = [
    ("2024-06-01", "2024-09-30"),   # coincides with a Sentinel-2 monsoon gap window
    ("2025-06-01", "2025-09-30"),
]

_OUTPUT_DIR = Path(__file__).parents[1] / "data" / "incoming" / "sentinel1"


def acquire_sentinel1(
    output_dir: Optional[Path] = None,
    date_ranges: Optional[List[tuple]] = None,
    bbox: Optional[List[float]] = None,
    region: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_bbox = resolve_bbox(region_name=region, bbox=bbox)
    return acquire_from_copernicus(
        collection="SENTINEL-1",
        underlying_dataset="Sentinel-1 GRD",
        date_ranges=date_ranges or _SENTINEL1_DATE_RANGES,
        output_dir=output_dir or _OUTPUT_DIR,
        bbox=resolved_bbox,
        cloud_cover_max=None,      # SAR has no cloud cover concept
        product_type="GRD",
        license_text="Copernicus open data licence (CC BY 4.0)",
    )


import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Acquire Sentinel-1 GRD SAR scenes.")
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Target region: salt_lake_sector_5, new_town_rajarhat, howrah_central",
    )
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        default=None,
        help="Custom bounding box coordinates",
    )
    args = parser.parse_args()

    result = acquire_sentinel1(region=args.region, bbox=args.bbox)
    if result["downloaded"] < 1:
        print(
            "\n[WARN] WARNING: No Sentinel-1 GRD scene downloaded. "
            "The SAR false-alarm-suppression demo will fall back to optical-only mode. "
            f"Gaps: {result['gaps']}"
        )
    else:
        print(f"\n[OK] Sentinel-1: {result['downloaded']} SAR scene(s) ready.")
