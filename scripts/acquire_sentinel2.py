"""
Acquire Sentinel-2 L2A imagery for the TerreX demo AOI (New Town / Salt Lake,
Kolkata) via the Copernicus Data Space Ecosystem OData API.

Target: ≥ 3 distinct dates spanning 2024–2026, cloud cover ≤ 20%.
One best-cloud scene is downloaded per 3-month window; gaps are logged,
never silently filled with a different AOI or relaxed threshold.

Usage:
  python scripts/acquire_sentinel2.py

Required env vars (set in .env or shell):
  COPERNICUS_USERNAME   — CDSE account email
  COPERNICUS_PASSWORD   — CDSE account password
  OR
  COPERNICUS_CLIENT_ID  + COPERNICUS_CLIENT_SECRET  (OAuth2 client-credentials)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from acquisition_common import acquire_from_copernicus, dense_revisit_windows, resolve_bbox
except ImportError:
    from scripts.acquisition_common import acquire_from_copernicus, dense_revisit_windows, resolve_bbox  # type: ignore

# ---------------------------------------------------------------------------
# Target date windows — default to most recent clear season (2026)
# Dense 5-day cadence ensures temporal diversity for the time-series demo
# ---------------------------------------------------------------------------
_SENTINEL2_DATE_RANGES: List[tuple] = dense_revisit_windows("2026-01-01", "2026-04-30", 5)

_OUTPUT_DIR = Path(__file__).parents[1] / "data" / "incoming" / "sentinel2"


def acquire_sentinel2(
    output_dir: Optional[Path] = None,
    date_ranges: Optional[List[tuple]] = None,
    bbox: Optional[List[float]] = None,
    region: Optional[str] = None,
    cloud_cover_max: float = 20.0,
) -> Dict[str, Any]:
    resolved_bbox = resolve_bbox(region_name=region, bbox=bbox)
    return acquire_from_copernicus(
        collection="SENTINEL-2",
        underlying_dataset="Sentinel-2 L2A",
        date_ranges=date_ranges or _SENTINEL2_DATE_RANGES,
        output_dir=output_dir or _OUTPUT_DIR,
        bbox=resolved_bbox,
        cloud_cover_max=cloud_cover_max,
        product_type="MSIL2A",   # L2A surface reflectance
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
    parser = argparse.ArgumentParser(description="Acquire Sentinel-2 L2A scenes.")
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
        help="Start date (YYYY-MM-DD), default: 2026-01-01",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD), default: 2026-04-30",
    )
    parser.add_argument(
        "--cadence-days",
        type=int,
        default=5,
        help="Revisit window size in days (default: 5)",
    )
    parser.add_argument(
        "--cloud-cover-max",
        type=float,
        default=20.0,
        help="Maximum cloud cover percentage (default: 20.0)",
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

    result = acquire_sentinel2(
        region=args.region,
        bbox=args.bbox,
        date_ranges=date_ranges,
        cloud_cover_max=args.cloud_cover_max,
    )
    covered = result["downloaded"]
    if covered < 3:
        print(
            f"\n[WARN] WARNING: Only {covered}/6 Sentinel-2 scenes downloaded. "
            f"TerreX needs >= 3 distinct dates for the time-series demo. "
            f"Gaps: {result['gaps']}"
        )
    else:
        print(f"\n[OK] Sentinel-2: {covered} scenes -- sufficient for time-series demo.")
