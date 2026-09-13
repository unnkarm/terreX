"""
Acquire Landsat 8/9 Collection 2 Level-2 imagery for the TerreX demo AOI
via the USGS EarthExplorer Machine-to-Machine (M2M) API.

Role: GAP-FILL ONLY — used for date windows where Sentinel-2 has no usable
scene for the AOI.  Does NOT duplicate Sentinel-2 dates unless explicitly
requested for cross-sensor comparison.

Usage:
  python scripts/acquire_landsat.py

Required env vars:
  USGS_USERNAME       — USGS ERS account username
  USGS_M2M_API_KEY    — 64-char Application Token from ERS profile
                        (https://ers.cr.usgs.gov/profile/access)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from acquisition_common import acquire_from_usgs, DEFAULT_BBOX, resolve_bbox
except ImportError:
    from scripts.acquisition_common import acquire_from_usgs, DEFAULT_BBOX, resolve_bbox  # type: ignore

# Date windows to attempt Landsat coverage.
# acquire_from_usgs() will skip any window that Sentinel-2 already covered
# when called from acquire_all.py (via the covered_s2_months argument).
_LANDSAT_DATE_RANGES: List[tuple] = [
    ("2024-01-01", "2024-04-30"),
    ("2024-06-01", "2024-09-30"),
    ("2024-10-01", "2024-12-31"),
    ("2025-01-01", "2025-04-30"),
    ("2025-07-01", "2025-10-31"),
    ("2025-11-01", "2026-03-31"),
]

_OUTPUT_DIR = Path(__file__).parents[1] / "data" / "incoming" / "landsat"


def acquire_landsat(
    output_dir: Optional[Path] = None,
    date_ranges: Optional[List[tuple]] = None,
    bbox: Optional[List[float]] = None,
    region: Optional[str] = None,
    cloud_cover_max: float = 20.0,
    skip_dates_if_covered: Optional[List[str]] = None,
) -> Dict[str, Any]:
    resolved_bbox = resolve_bbox(region_name=region, bbox=bbox)
    return acquire_from_usgs(
        dataset="landsat_ot_c2_l2",
        underlying_dataset="Landsat 8/9 C2L2",
        date_ranges=date_ranges or _LANDSAT_DATE_RANGES,
        output_dir=output_dir or _OUTPUT_DIR,
        bbox=resolved_bbox,
        cloud_cover_max=cloud_cover_max,
        skip_dates_if_covered=skip_dates_if_covered,
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
    parser = argparse.ArgumentParser(description="Acquire Landsat 8/9 C2L2 scenes.")
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

    result = acquire_landsat(region=args.region, bbox=args.bbox)
    print(
        f"\nLandsat gap-fill: {result['downloaded']} scene(s) downloaded "
        f"({len(result['gaps'])} gaps, {len(result['errors'])} errors)"
    )
