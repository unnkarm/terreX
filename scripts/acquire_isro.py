"""
Bhoonidhi (ISRO) satellite imagery acquisition for TerreX.

Acquires supplementary Indian EO imagery:
  1. Resourcesat-2 / AWiFS     (56m regional context)
  2. Resourcesat-2 / LISS-III  (23.5m multispectral)
  3. Resourcesat-2 / LISS-IV   (5.8m high-resolution optical)
  4. Cartosat-2S / PAN         (0.65m very high resolution)

Notes:
  - Bhoonidhi is a supplementary source (same agency as PS-named Bhuvan).
  - Online=Y scenes are downloaded automatically.
  - Online=N scenes are logged as 'delayed - human may order manually'.
  - Generates strict .provenance.json sidecar with ps_named_source=False.

Credentials (read from .env or shell):
  BHOONIDHI_USER
  BHOONIDHI_PASS
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from acquisition_common import acquire_from_isro, DEFAULT_BBOX
except ImportError:
    from scripts.acquisition_common import acquire_from_isro, DEFAULT_BBOX  # type: ignore

_DEFAULT_OUTPUT = Path(__file__).parents[1] / "data" / "incoming" / "isro"

# Target quarterly date ranges
_DEFAULT_DATE_RANGES = [
    ("2024-01-01", "2024-04-30"),
    ("2024-09-01", "2024-12-31"),
    ("2025-01-01", "2025-04-30"),
]


def acquire_isro(
    output_dir: Optional[Path] = None,
    bbox: Optional[List[float]] = None,
    cloud_cover_max: float = 20.0,
    date_ranges: Optional[List[tuple]] = None,
) -> Dict[str, Any]:
    """
    Acquire supplementary ISRO imagery from Bhoonidhi portal.
    """
    dest_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT
    dest_dir.mkdir(parents=True, exist_ok=True)
    ranges = date_ranges or _DEFAULT_DATE_RANGES
    effective_bbox = bbox or DEFAULT_BBOX

    print("=" * 60)
    print("ISRO / Bhoonidhi Acquisition (Supplementary Source)")
    print(f"Target AOI: {effective_bbox}")
    print("=" * 60)

    # 1. LISS-IV (5.8m high-res optical)
    print("\n-- ISRO Resourcesat-2 LISS-IV (5.8m Optical) --")
    liss4_summary = acquire_from_isro(
        dataset_label="liss4",
        underlying_dataset="LISS-IV",
        satellite="Resourcesat-2",
        sensor="LISS-IV",
        date_ranges=ranges,
        output_dir=dest_dir,
        bbox=effective_bbox,
        cloud_cover_max=cloud_cover_max,
    )

    # 2. LISS-III (23.5m multispectral)
    print("\n-- ISRO Resourcesat-2 LISS-III (23.5m Multispectral) --")
    liss3_summary = acquire_from_isro(
        dataset_label="liss3",
        underlying_dataset="LISS-III",
        satellite="Resourcesat-2",
        sensor="LISS-III",
        date_ranges=ranges,
        output_dir=dest_dir,
        bbox=effective_bbox,
        cloud_cover_max=cloud_cover_max,
    )

    # 3. AWiFS (56m regional context)
    print("\n-- ISRO Resourcesat-2 AWiFS (56m Regional) --")
    awifs_summary = acquire_from_isro(
        dataset_label="awifs",
        underlying_dataset="AWiFS",
        satellite="Resourcesat-2",
        sensor="AWiFS",
        date_ranges=ranges,
        output_dir=dest_dir,
        bbox=effective_bbox,
        cloud_cover_max=cloud_cover_max,
    )

    # 4. Cartosat-2S (0.65m VHR PAN)
    print("\n-- ISRO Cartosat-2S (0.65m VHR PAN) --")
    carto_summary = acquire_from_isro(
        dataset_label="cartosat",
        underlying_dataset="Cartosat-2S",
        satellite="Cartosat-2S",
        sensor="PAN",
        date_ranges=ranges,
        output_dir=dest_dir,
        bbox=effective_bbox,
        cloud_cover_max=cloud_cover_max,
    )

    summaries = [liss4_summary, liss3_summary, awifs_summary, carto_summary]
    return {
        "source": "isro-bhoonidhi",
        "found": sum(s["found"] for s in summaries),
        "downloaded": sum(s["downloaded"] for s in summaries),
        "skipped_delayed": sum(s["skipped_delayed"] for s in summaries),
        "delayed": [d for s in summaries for d in s["delayed"]],
        "gaps": [g for s in summaries for g in s["gaps"]],
        "errors": [e for s in summaries for e in s["errors"]],
        "products": summaries,
    }


if __name__ == "__main__":
    acquire_isro()
