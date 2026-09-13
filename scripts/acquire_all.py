"""
TerreX unified dataset acquisition entrypoint.

Runs all three acquisition sources in order:
  1. Copernicus → Sentinel-2 L2A  (primary backbone, 2024–2026)
  2. Copernicus → Sentinel-1 GRD  (SAR for monsoon/cloud scenes)
  3. USGS M2M  → Landsat 8/9 C2L2 (gap-fill for Sentinel-2 gaps only)

Exits non-zero and prints a loud warning if fewer than 3 distinct Sentinel-2
dates are acquired — that's the minimum needed for the time-series demo.

Usage:
  python scripts/acquire_all.py

  # Optional: dry-run (shows what would be acquired, no downloads)
  DRY_RUN=1 python scripts/acquire_all.py

Required env vars (in .env or shell):
  COPERNICUS_USERNAME + COPERNICUS_PASSWORD  (or CLIENT_ID + CLIENT_SECRET)
  USGS_USERNAME + USGS_M2M_API_KEY
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure scripts/ is on the path when run from project root
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[1] / ".env")
except ImportError:
    pass

try:
    from acquire_sentinel2 import acquire_sentinel2
    from acquire_sentinel1 import acquire_sentinel1
    from acquire_landsat import acquire_landsat
    from validate_provenance import validate_incoming_directory
except ImportError:
    from scripts.acquire_sentinel2 import acquire_sentinel2  # type: ignore
    from scripts.acquire_sentinel1 import acquire_sentinel1  # type: ignore
    from scripts.acquire_landsat import acquire_landsat  # type: ignore
    from scripts.validate_provenance import validate_incoming_directory  # type: ignore

_MIN_SENTINEL2_DATES = 3
_INCOMING_DIR = Path(__file__).parents[1] / "data" / "incoming"


def _covered_dates() -> List[str]:
    """Extract YYYY-MM-DD strings for all available Sentinel-2 scenes in incoming."""
    covered = []
    for sidecar in _INCOMING_DIR.rglob("*.provenance.json"):
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            sat = str(data.get("satellite", "")).lower()
            ds = str(data.get("underlying_dataset", "")).lower()
            if "sentinel-2" in sat or "sentinel-2" in ds:
                acq = str(data.get("acquisition_date", ""))[:10]
                if acq:
                    covered.append(acq)
        except Exception:
            pass
    return sorted(list(set(covered)))


import argparse

def main() -> int:
    parser = argparse.ArgumentParser(description="TerreX unified dataset acquisition entrypoint.")
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
        "--include-isro",
        action="store_true",
        default=False,
        help="Query ISRO Bhoonidhi supplementary portal",
    )
    args, _ = parser.parse_known_args()

    print("=" * 60)
    print("TerreX Dataset Acquisition -- Copernicus + USGS M2M")
    if args.region:
        print(f"Target Region: {args.region}")
    if args.bbox:
        print(f"Target BBox  : {args.bbox}")
    print("=" * 60)

    dry_run = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
    if dry_run:
        print("DRY_RUN mode -- no files will be downloaded.\n")

    include_isro = args.include_isro or os.getenv("INCLUDE_ISRO", "").lower() in ("1", "true", "yes")

    # ---------------------------------------------------------------
    # Step 1: Sentinel-2 (primary backbone)
    # ---------------------------------------------------------------
    print("\n-- Sentinel-2 L2A (primary) --")
    s2_summary = acquire_sentinel2(region=args.region, bbox=args.bbox)

    # ---------------------------------------------------------------
    # Step 2: Sentinel-1 (SAR, monsoon corroboration)
    # ---------------------------------------------------------------
    print("\n-- Sentinel-1 GRD (SAR) --")
    s1_summary = acquire_sentinel1(region=args.region, bbox=args.bbox)

    # ---------------------------------------------------------------
    # Step 3: Landsat (gap-fill for dates Sentinel-2 missed)
    # ---------------------------------------------------------------
    s2_dates = _covered_dates()
    print(f"\n-- Landsat 8/9 C2L2 (gap-fill; S2 dates covered: {s2_dates}) --")
    ls_summary = acquire_landsat(region=args.region, bbox=args.bbox, skip_dates_if_covered=s2_dates)

    # ---------------------------------------------------------------
    # Step 3b (Optional): ISRO Bhoonidhi Supplementary
    # ---------------------------------------------------------------
    isro_summary = None
    if include_isro:
        print("\n-- ISRO / Bhoonidhi (Supplementary Source) --")
        try:
            try:
                from acquire_isro import acquire_isro
            except ImportError:
                from scripts.acquire_isro import acquire_isro  # type: ignore
            isro_summary = acquire_isro()
        except Exception as exc:
            print(f"[WARN] Bhoonidhi supplementary acquisition skipped: {exc}")
            isro_summary = {"source": "isro-bhoonidhi", "found": 0, "downloaded": 0, "gaps": [], "errors": [str(exc)]}
    else:
        print("\n-- ISRO / Bhoonidhi --")
        print("  Skipped (pass --include-isro to query Bhoonidhi supplementary portal)")

    # ---------------------------------------------------------------
    # Step 4: Provenance validation
    # ---------------------------------------------------------------
    print("\n-- Provenance validation --")
    prov_errors = validate_incoming_directory(_INCOMING_DIR)
    if prov_errors:
        print("[WARN] PROVENANCE ERRORS -- these files will be rejected by ingestion:")
        for err in prov_errors:
            print(f"   {err}")
    else:
        print("[OK]  All downloaded files have valid provenance sidecars.")

    # ---------------------------------------------------------------
    # Step 5: Consolidated report
    # ---------------------------------------------------------------
    all_summaries = [s2_summary, s1_summary, ls_summary]
    if isro_summary:
        all_summaries.append(isro_summary)
    total_downloaded = sum(s["downloaded"] for s in all_summaries)
    total_errors = sum(len(s["errors"]) for s in all_summaries)
    all_gaps = {s["source"]: s["gaps"] for s in all_summaries if s["gaps"]}

    print("\n" + "=" * 60)
    print("ACQUISITION REPORT")
    print("=" * 60)
    for s in all_summaries:
        status = "[OK]" if s["downloaded"] > 0 else "[--]"
        print(
            f"  {status:5s} {s['source']:35s}  found={s['found']}  "
            f"downloaded={s['downloaded']}  gaps={len(s['gaps'])}"
        )
    print(f"\n  Total scenes downloaded : {total_downloaded}")
    print(f"  Total errors            : {total_errors}")
    print(f"  Provenance errors       : {len(prov_errors)}")
    if all_gaps:
        print("\n  Open date gaps:")
        for source, gaps in all_gaps.items():
            for g in gaps:
                print(f"    {source}: {g}")

    # ---------------------------------------------------------------
    # Exit code
    # ---------------------------------------------------------------
    s2_count = s2_summary["downloaded"]
    if s2_count < _MIN_SENTINEL2_DATES:
        print(
            f"\n[WARN] CRITICAL: Only {s2_count} Sentinel-2 scene(s) downloaded. "
            f"TerreX requires >= {_MIN_SENTINEL2_DATES} distinct dates for the "
            "multi-temporal time-series demo (PS 2.2.2). "
            "Check gaps above and re-run after resolving credential / coverage issues."
        )
        return 1

    core_errors = sum(len(s["errors"]) for s in [s2_summary, s1_summary, ls_summary])
    if core_errors > 0 or prov_errors:
        print("\n[WARN] Core acquisition errors occurred. Review the log above before ingesting.")
        return 1

    if isro_summary and isro_summary.get("errors"):
        print("\n[NOTICE] Bhoonidhi supplementary acquisition reported errors/outages (non-blocking). Core pipeline remains ready.")

    print(
        f"\n[OK] Acquisition complete -- {total_downloaded} scenes ready in "
        f"data/incoming/. Run ingestion next:\n"
        f"   curl -X POST http://localhost:8000/api/ingest/process-incoming"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
