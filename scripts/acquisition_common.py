"""
Shared utilities for TerreX satellite imagery acquisition scripts.

Provides:
  - DEFAULT_BBOX  — New Town / Salt Lake, Kolkata (consistent AOI)
  - write_provenance() — generates .provenance.json sidecar for every downloaded file
  - acquire_from_copernicus() — high-level workflow for Copernicus sources
  - acquire_from_usgs()       — high-level workflow for USGS M2M sources

Network calls are intentionally confined to this module + the client modules.
None of these utilities are imported by backend/ runtime code.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Canonical AOI & Regional Bounding Boxes [minLon, minLat, maxLon, maxLat]
# ---------------------------------------------------------------------------
DEFAULT_BBOX: List[float] = [88.40, 22.56, 88.48, 22.62]
OPERATIONAL_BOUNDS: List[float] = [87.75, 21.40, 88.65, 23.60]

REGION_BBOXES: Dict[str, List[float]] = {
    "salt_lake_sector_5": [88.415, 22.565, 88.445, 22.590],
    "new_town_rajarhat": [88.455, 22.575, 88.500, 22.625],
    "howrah_central": [88.28, 22.55, 88.35, 22.62],
}

REGION_ALIASES: Dict[str, str] = {
    "salt_lake": "salt_lake_sector_5",
    "saltlake": "salt_lake_sector_5",
    "sector_5": "salt_lake_sector_5",
    "sector5": "salt_lake_sector_5",
    "sector_v": "salt_lake_sector_5",
    "new_town": "new_town_rajarhat",
    "newtown": "new_town_rajarhat",
    "rajarhat": "new_town_rajarhat",
    "howrah": "howrah_central",
    "howrah_station": "howrah_central",
}


def resolve_bbox(region_name: Optional[str] = None, bbox: Optional[List[float]] = None) -> List[float]:
    """Resolve bounding box from explicit list, named region, or default."""
    if bbox is not None:
        resolved = bbox
        if len(resolved) != 4 or resolved[0] >= resolved[2] or resolved[1] >= resolved[3]:
            raise ValueError("bbox must be [min_lon, min_lat, max_lon, max_lat]")
        if not (
            OPERATIONAL_BOUNDS[0] <= resolved[0]
            and OPERATIONAL_BOUNDS[1] <= resolved[1]
            and resolved[2] <= OPERATIONAL_BOUNDS[2]
            and resolved[3] <= OPERATIONAL_BOUNDS[3]
        ):
            raise ValueError(
                f"bbox must stay inside the Greater Kolkata / West Bengal operational boundary {OPERATIONAL_BOUNDS}"
            )
        return resolved
    if region_name:
        key = region_name.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")
        canonical = REGION_ALIASES.get(key, key)
        if canonical in REGION_BBOXES:
            return REGION_BBOXES[canonical]
        raise ValueError(
            f"Unknown region '{region_name}'. Known regions: {list(REGION_BBOXES.keys())} or aliases {list(REGION_ALIASES.keys())}"
        )
    return DEFAULT_BBOX


def dense_revisit_windows(start_date: str, end_date: str, cadence_days: int) -> List[tuple]:
    """Build non-overlapping acquisition windows at the nominal revisit cadence."""
    if cadence_days < 1:
        raise ValueError("cadence_days must be positive")
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        raise ValueError("end_date must not precede start_date")
    windows: List[tuple] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=cadence_days - 1), end)
        windows.append((cursor.isoformat(), window_end.isoformat()))
        cursor += timedelta(days=cadence_days)
    return windows


def download_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Provenance sidecar
# ---------------------------------------------------------------------------

def write_provenance(
    raster_path: Path,
    source_portal: str,
    underlying_dataset: str,
    satellite: str,
    sensor: str,
    acquisition_date: str,
    resolution_m: float,
    bbox: List[float],
    license_text: str,
    cloud_cover_pct: Optional[float],
    notes: str = "",
    ps_named_source: bool = True,
) -> Path:
    """
    Write a .provenance.json sidecar beside raster_path.

    The schema matches what backend/services/ingestion.py's _load_provenance()
    and scripts/validate_provenance.py's ProvenanceMetadata expect.
    """
    payload = {
        "source_portal": source_portal,
        "underlying_dataset": underlying_dataset,
        "satellite": satellite,
        "sensor": sensor,
        "acquisition_date": acquisition_date,
        "resolution_m": resolution_m,
        "bounding_box": bbox,
        "license": license_text,
        "download_date": download_date(),
        "cloud_cover_pct": cloud_cover_pct,
        "ps_named_source": ps_named_source,
        "notes": notes,
    }
    sidecar = raster_path.with_name(f"{raster_path.stem}.provenance.json")
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return sidecar


# ---------------------------------------------------------------------------
# Copernicus acquisition workflow
# ---------------------------------------------------------------------------

def acquire_from_copernicus(
    collection: str,
    underlying_dataset: str,
    date_ranges: List[tuple],      # list of (start_date, end_date) strings
    output_dir: Path,
    bbox: Optional[List[float]] = None,
    cloud_cover_max: Optional[float] = 20.0,
    product_type: Optional[str] = None,
    license_text: str = "Copernicus open data licence (CC BY 4.0)",
) -> Dict[str, Any]:
    """
    Generic Copernicus acquisition: search each date-range → pick best scene
    → download → write provenance sidecar.

    Returns a summary dict compatible with acquire_all.py's report format.
    """
    try:
        from copernicus_client import CopernicusClient, CopernicusError
    except ImportError:
        from scripts.copernicus_client import CopernicusClient, CopernicusError  # type: ignore

    source_label = f"copernicus-{collection.lower()}"
    summary: Dict[str, Any] = {
        "source": source_label,
        "collection": collection,
        "found": 0,
        "downloaded": 0,
        "skipped_delayed": 0,
        "gaps": [],
        "errors": [],
    }

    try:
        client = CopernicusClient()
        client.authenticate()
    except CopernicusError as exc:
        summary["errors"].append(str(exc))
        summary["gaps"] = [f"{s}->{e}" for s, e in date_ranges]
        print(f"[{source_label}] acquisition unavailable: {exc}")
        return summary

    output_dir.mkdir(parents=True, exist_ok=True)
    effective_bbox = bbox or DEFAULT_BBOX

    for start_date, end_date in date_ranges:
        range_label = f"{start_date[:7]}..{end_date[:7]}"
        try:
            scenes = client.search(
                bbox=effective_bbox,
                start_date=start_date,
                end_date=end_date,
                collection=collection,
                cloud_cover_max=cloud_cover_max,
                product_type=product_type,
                max_results=10,
            )
        except CopernicusError as exc:
            summary["errors"].append(f"{range_label}: {exc}")
            summary["gaps"].append(range_label)
            print(f"[{source_label}] {range_label}: search error -- {exc}")
            continue

        online_scenes = [s for s in scenes if s.get("online", True)]
        summary["found"] += len(scenes)
        offline_count = len(scenes) - len(online_scenes)
        if offline_count:
            summary["skipped_delayed"] += offline_count

        if not online_scenes:
            summary["gaps"].append(range_label)
            reason = "offline only" if scenes else "no coverage / cloud threshold"
            print(f"[{source_label}] {range_label}: {reason} (found {len(scenes)} total)")
            continue

        # Pick scene with least cloud cover (or first for SAR)
        best = sorted(
            online_scenes,
            key=lambda s: float(s["cloud_cover"] or 0) if s["cloud_cover"] is not None else 0,
        )[0]
        product_id = best["product_id"]
        safe_name = best["name"].replace("/", "_").replace("\\", "_")
        dest = output_dir / f"{safe_name[:80]}.tif"

        if dest.exists():
            sidecar = dest.with_name(f"{dest.stem}.provenance.json")
            if sidecar.exists():
                print(f"[{source_label}] {range_label}: already downloaded -> {dest.name}")
                summary["downloaded"] += 1
                continue

        dry_run = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
        if dry_run:
            print(f"[{source_label}] {range_label}: [DRY_RUN] would download {best['acquisition_date']} (cloud={best['cloud_cover']}%) -> {dest.name}")
            summary["downloaded"] += 1
            continue

        try:
            client.download(product_id, dest)
            write_provenance(
                raster_path=dest,
                source_portal="Copernicus Data Space Ecosystem",
                underlying_dataset=underlying_dataset,
                satellite=best["satellite"],
                sensor=best["sensor"],
                acquisition_date=best["acquisition_date"],
                resolution_m=best["resolution_m"],
                bbox=list(best["bbox"]),
                license_text=license_text,
                cloud_cover_pct=best["cloud_cover"],
                notes=f"Product ID: {product_id}; Name: {best['name']}",
            )
            summary["downloaded"] += 1
            print(
                f"[{source_label}] {range_label}: [OK] {best['acquisition_date']} "
                f"cloud={best['cloud_cover']}% -> {dest.name}"
            )
        except CopernicusError as exc:
            summary["errors"].append(f"{range_label}/{product_id}: {exc}")
            print(f"[{source_label}] {range_label}: download error -- {exc}")
            if dest.exists() and dest.stat().st_size == 0:
                dest.unlink(missing_ok=True)

    _print_summary(source_label, summary)
    return summary


# ---------------------------------------------------------------------------
# USGS acquisition workflow
# ---------------------------------------------------------------------------

def is_window_covered(start_date: str, end_date: str, covered_dates: List[str]) -> bool:
    """Check if any covered date falls within [start_date, end_date]."""
    for d in covered_dates:
        if start_date[:10] <= d[:10] <= end_date[:10]:
            return True
    return False


def acquire_from_usgs(
    dataset: str,
    underlying_dataset: str,
    date_ranges: List[tuple],
    output_dir: Path,
    bbox: Optional[List[float]] = None,
    cloud_cover_max: Optional[float] = 20.0,
    skip_dates_if_covered: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    USGS M2M acquisition: scene-search -> download -> provenance sidecar.
    Skips date ranges already covered by Copernicus (pass list of covered dates).
    """
    try:
        from usgs_client import USGSClient, USGSError
    except ImportError:
        from scripts.usgs_client import USGSClient, USGSError  # type: ignore

    source_label = f"usgs-{dataset}"
    summary: Dict[str, Any] = {
        "source": source_label,
        "dataset": dataset,
        "found": 0,
        "downloaded": 0,
        "gaps": [],
        "errors": [],
    }

    covered = skip_dates_if_covered or []

    # Check if all date ranges are already covered before even authenticating
    active_ranges = []
    for start_date, end_date in date_ranges:
        range_label = f"{start_date[:7]}..{end_date[:7]}"
        if covered and is_window_covered(start_date, end_date, covered):
            print(f"[{source_label}] {range_label}: skipping (Sentinel-2 already covers this window)")
        else:
            active_ranges.append((start_date, end_date))

    if not active_ranges:
        _print_summary(source_label, summary)
        return summary

    try:
        client = USGSClient()
        client.authenticate()
    except USGSError as exc:
        summary["errors"].append(str(exc))
        summary["gaps"] = [f"{s}->{e}" for s, e in active_ranges]
        print(f"[{source_label}] acquisition unavailable: {exc}")
        return summary

    output_dir.mkdir(parents=True, exist_ok=True)
    effective_bbox = bbox or DEFAULT_BBOX

    for start_date, end_date in active_ranges:
        range_label = f"{start_date[:7]}..{end_date[:7]}"

        try:
            scenes = client.search(
                bbox=effective_bbox,
                start_date=start_date,
                end_date=end_date,
                dataset=dataset,
                cloud_cover_max=cloud_cover_max,
                max_results=10,
            )
        except USGSError as exc:
            summary["errors"].append(f"{range_label}: {exc}")
            summary["gaps"].append(range_label)
            print(f"[{source_label}] {range_label}: search error -- {exc}")
            continue

        summary["found"] += len(scenes)

        if not scenes:
            summary["gaps"].append(range_label)
            print(f"[{source_label}] {range_label}: no coverage under cloud threshold")
            continue

        best = sorted(
            scenes,
            key=lambda s: float(s["cloud_cover"] or 0) if s["cloud_cover"] is not None else 0,
        )[0]
        entity_id = best["entity_id"]
        dest = output_dir / f"{entity_id}.tif"

        if dest.exists():
            sidecar = dest.with_name(f"{dest.stem}.provenance.json")
            if sidecar.exists():
                print(f"[{source_label}] {range_label}: already downloaded -> {dest.name}")
                summary["downloaded"] += 1
                continue

        dry_run = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
        if dry_run:
            print(f"[{source_label}] {range_label}: [DRY_RUN] would download {best['acquisition_date']} (cloud={best['cloud_cover']}%) -> {dest.name}")
            summary["downloaded"] += 1
            continue

        try:
            client.download(entity_id, dest, dataset=dataset)
            write_provenance(
                raster_path=dest,
                source_portal="USGS EarthExplorer (M2M)",
                underlying_dataset=underlying_dataset,
                satellite=best["satellite"],
                sensor=best["sensor"],
                acquisition_date=best["acquisition_date"],
                resolution_m=best["resolution_m"],
                bbox=list(best["bbox"]),
                license_text="USGS Landsat data are in the public domain",
                cloud_cover_pct=best["cloud_cover"],
                notes=f"entityId: {entity_id}; displayId: {best.get('display_id')}",
            )
            summary["downloaded"] += 1
            print(
                f"[{source_label}] {range_label}: [OK] {best['acquisition_date']} "
                f"cloud={best['cloud_cover']}% -> {dest.name}"
            )
        except USGSError as exc:
            summary["errors"].append(f"{range_label}/{entity_id}: {exc}")
            print(f"[{source_label}] {range_label}: download error -- {exc}")
            if dest.exists() and dest.stat().st_size == 0:
                dest.unlink(missing_ok=True)

    try:
        client.logout()
    except Exception:
        pass

    _print_summary(source_label, summary)
    return summary


# ---------------------------------------------------------------------------
# Bhoonidhi (ISRO) acquisition workflow
# ---------------------------------------------------------------------------

def acquire_from_isro(
    dataset_label: str,
    underlying_dataset: str,
    satellite: str,
    sensor: str,
    date_ranges: List[tuple],
    output_dir: Path,
    bbox: Optional[List[float]] = None,
    cloud_cover_max: Optional[float] = 20.0,
    license_text: str = "ISRO Bhoonidhi Open Data Terms",
) -> Dict[str, Any]:
    """
    Bhoonidhi acquisition workflow: search -> filter online (Online=Y) -> download -> write provenance sidecar.
    Online=N matches are logged as 'available but delayed -- human may order manually'.
    """
    try:
        from bhoonidhi_client import BhoonidhiClient, BhoonidhiError, DelayedProductError
    except ImportError:
        from scripts.bhoonidhi_client import BhoonidhiClient, BhoonidhiError, DelayedProductError  # type: ignore

    source_label = f"isro-{dataset_label.lower()}"
    summary: Dict[str, Any] = {
        "source": source_label,
        "dataset": underlying_dataset,
        "found": 0,
        "downloaded": 0,
        "skipped_delayed": 0,
        "delayed": [],
        "gaps": [],
        "errors": [],
    }

    try:
        client = BhoonidhiClient()
        client.authenticate()
    except BhoonidhiError as exc:
        summary["errors"].append(str(exc))
        summary["gaps"] = [f"{s}->{e}" for s, e in date_ranges]
        print(f"[{source_label}] Bhoonidhi acquisition unavailable: {exc}")
        return summary

    output_dir.mkdir(parents=True, exist_ok=True)
    effective_bbox = bbox or DEFAULT_BBOX

    for start_date, end_date in date_ranges:
        range_label = f"{start_date[:7]}..{end_date[:7]}"
        try:
            scenes = client.search(
                bbox=effective_bbox,
                start_date=start_date,
                end_date=end_date,
                satellite=satellite,
                sensor=sensor,
                cloud_cover_max=cloud_cover_max,
            )
        except BhoonidhiError as exc:
            summary["errors"].append(f"{range_label}: {exc}")
            summary["gaps"].append(range_label)
            print(f"[{source_label}] {range_label}: search error -- {exc}")
            continue

        summary["found"] += len(scenes)
        online_scenes = [s for s in scenes if s.get("online_status") == "Y"]
        delayed_scenes = [s for s in scenes if s.get("online_status") != "Y"]

        if delayed_scenes:
            summary["skipped_delayed"] += len(delayed_scenes)
            for d in delayed_scenes:
                msg = f"Scene {d.get('scene_id')} ({d.get('acquisition_date')}): available but delayed (Online=N) -- human may order manually via Bhoonidhi portal."
                summary["delayed"].append(msg)
                print(f"[{source_label}] [DELAYED] {msg}")

        if not online_scenes:
            summary["gaps"].append(range_label)
            reason = "delayed/offline products only" if scenes else "no coverage / cloud threshold"
            print(f"[{source_label}] {range_label}: {reason} (found {len(scenes)} total)")
            continue

        best = sorted(
            online_scenes,
            key=lambda s: float(s["cloud_cover"] or 0) if s["cloud_cover"] is not None else 0,
        )[0]
        scene_id = best["scene_id"]
        safe_name = f"{underlying_dataset.replace(' ', '_')}_{scene_id}_{best['acquisition_date']}"
        dest = output_dir / f"{safe_name}.tif"

        if dest.exists():
            sidecar = dest.with_name(f"{dest.stem}.provenance.json")
            if sidecar.exists():
                print(f"[{source_label}] {range_label}: already downloaded -> {dest.name}")
                summary["downloaded"] += 1
                continue

        dry_run = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
        if dry_run:
            print(f"[{source_label}] {range_label}: [DRY_RUN] would download {best['acquisition_date']} (cloud={best['cloud_cover']}%) -> {dest.name}")
            summary["downloaded"] += 1
            continue

        try:
            client.download(scene_id, dest)
            write_provenance(
                raster_path=dest,
                source_portal="Bhoonidhi",
                underlying_dataset=underlying_dataset,
                satellite=best.get("satellite") or satellite,
                sensor=best.get("sensor") or sensor,
                acquisition_date=best["acquisition_date"],
                resolution_m=float(best.get("resolution") or 5.8),
                bbox=list(best["bbox"]),
                license_text=license_text,
                cloud_cover_pct=best.get("cloud_cover"),
                notes="supplementary — same agency as PS-named Bhuvan, not itself explicitly named in PS §7.1",
                ps_named_source=False,
            )
            summary["downloaded"] += 1
            print(
                f"[{source_label}] {range_label}: [OK] {best['acquisition_date']} "
                f"cloud={best.get('cloud_cover')}% -> {dest.name}"
            )
        except BhoonidhiError as exc:
            summary["errors"].append(f"{range_label}/{scene_id}: {exc}")
            print(f"[{source_label}] {range_label}: download error -- {exc}")
            if dest.exists() and dest.stat().st_size == 0:
                dest.unlink(missing_ok=True)

    _print_summary(source_label, summary)
    return summary


def _print_summary(label: str, s: Dict[str, Any]) -> None:
    print(
        f"[{label}] DONE -- found={s['found']} downloaded={s['downloaded']} "
        f"gaps={len(s['gaps'])} errors={len(s['errors'])}"
    )
