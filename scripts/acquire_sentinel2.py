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
    from acquisition_common import acquire_from_copernicus, DEFAULT_BBOX, resolve_bbox
except ImportError:
    from scripts.acquisition_common import acquire_from_copernicus, DEFAULT_BBOX, resolve_bbox  # type: ignore

# ---------------------------------------------------------------------------
# Target date windows — one scene per quarter ensures temporal diversity
# for the 6-pass "Military Time Machine" demo (PS requirement §2.2.2)
# ---------------------------------------------------------------------------
_SENTINEL2_DATE_RANGES: List[tuple] = [
    ("2024-01-01", "2024-04-30"),
    ("2024-06-01", "2024-09-30"),
    ("2024-10-01", "2024-12-31"),
    ("2025-01-01", "2025-04-30"),
    ("2025-07-01", "2025-10-31"),
    ("2025-11-01", "2026-03-31"),
]

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
    args = parser.parse_args()

    result = acquire_sentinel2(region=args.region, bbox=args.bbox)
    covered = result["downloaded"]
    if covered < 3:
        print(
            f"\n[WARN] WARNING: Only {covered}/6 Sentinel-2 scenes downloaded. "
            f"TerreX needs >= 3 distinct dates for the time-series demo. "
            f"Gaps: {result['gaps']}"
        )
    else:
        print(f"\n[OK] Sentinel-2: {covered} scenes -- sufficient for time-series demo.")
