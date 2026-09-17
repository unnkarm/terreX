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
    from acquisition_common import acquire_from_copernicus, dense_revisit_windows, resolve_bbox
except ImportError:
    from scripts.acquisition_common import acquire_from_copernicus, dense_revisit_windows, resolve_bbox  # type: ignore

# Monsoon window — radar is most useful here; default to recent 2026 window
_SENTINEL1_DATE_RANGES: List[tuple] = dense_revisit_windows("2026-06-01", "2026-09-17", 6)

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
from datetime import datetime, timedelta
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
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD), default: 2026-06-01",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD), default: 2026-09-17",
    )
    parser.add_argument(
        "--cadence-days",
        type=int,
        default=6,
        help="Revisit window size in days (default: 6)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=None,
        help="Acquire scenes from the last N days up to today",
    )
    args = parser.parse_args()

    date_ranges = None
    if args.days_back:
        end_d = datetime.now().date()
        start_d = end_d - timedelta(days=args.days_back)
        date_ranges = dense_revisit_windows(start_d.isoformat(), end_d.isoformat(), args.cadence_days)
    elif args.start_date and args.end_date:
        date_ranges = dense_revisit_windows(args.start_date, args.end_date, args.cadence_days)
    elif args.start_date:
        end_d = datetime.now().date().isoformat()
        date_ranges = dense_revisit_windows(args.start_date, end_d, args.cadence_days)

    result = acquire_sentinel1(region=args.region, bbox=args.bbox, date_ranges=date_ranges)
    if result["downloaded"] < 1:
        print(
            "\n[WARN] WARNING: No Sentinel-1 GRD scene downloaded. "
            "The SAR false-alarm-suppression demo will fall back to optical-only mode. "
            f"Gaps: {result['gaps']}"
        )
    else:
        print(f"\n[OK] Sentinel-1: {result['downloaded']} SAR scene(s) ready.")
