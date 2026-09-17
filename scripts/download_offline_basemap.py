"""
CLI: Pre-download and cache satellite basemap XYZ tiles for 100% offline usage in TerreX.

Downloads high-resolution aerial/satellite tiles from Esri World Imagery directly into
data/offline_basemap/tiles/{z}/{x}/{y}.png so the platform can run completely disconnected.

Usage:
    # Pre-download Kolkata metropolitan area (zooms 8 to 14):
    python scripts/download_offline_basemap.py --aoi kolkata

    # Pre-download specific custom bounding box (min_lon, min_lat, max_lon, max_lat):
    python scripts/download_offline_basemap.py --bbox 88.20,22.40,88.55,22.70 --zoom-min 9 --zoom-max 15

    # Check offline basemap cache status:
    python scripts/download_offline_basemap.py --status
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Fix Windows terminal encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
BASEMAP_DIR = ROOT_DIR / "data" / "offline_basemap" / "tiles"

PRESET_AOIS = {
    "kolkata": {
        "name": "Kolkata Core Metropolitan & Hooghly River (~50x50 km)",
        "bbox": (88.15, 22.35, 88.60, 22.75),  # [min_lon, min_lat, max_lon, max_lat]
        "default_min_zoom": 8,
        "default_max_zoom": 14,
    },
    "kolkata_operational": {
        "name": "Greater Kolkata / West Bengal Operational Boundary",
        "bbox": (87.75, 21.40, 88.65, 23.60),
        "default_min_zoom": 7,
        "default_max_zoom": 14,
    },
}

TILE_URL_TEMPLATE = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    """Convert WGS84 lat/lon to Slippy Map tile numbers (X, Y)."""
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(int(n) - 1, xtile)), max(0, min(int(n) - 1, ytile))


def calculate_tile_list(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float, min_zoom: int, max_zoom: int
) -> list[tuple[int, int, int]]:
    """Generate all (z, x, y) tile coordinates for a bounding box across zoom levels."""
    tiles = []
    for z in range(min_zoom, max_zoom + 1):
        x_min, y_min = deg2num(max_lat, min_lon, z)
        x_max, y_max = deg2num(min_lat, max_lon, z)

        x_start, x_end = min(x_min, x_max), max(x_min, x_max)
        y_start, y_end = min(y_min, y_max), max(y_min, y_max)

        for x in range(x_start, x_end + 1):
            for y in range(y_start, y_end + 1):
                tiles.append((z, x, y))
    return tiles


def download_single_tile(z: int, x: int, y: int) -> tuple[bool, str]:
    """Download and cache a single XYZ tile."""
    tile_file = BASEMAP_DIR / str(z) / str(x) / f"{y}.png"
    if tile_file.exists() and tile_file.stat().st_size > 500:
        return True, "cached"

    url = TILE_URL_TEMPLATE.format(z=z, y=y, x=x)
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TerreX-Offline-Downloader/1.0"
            },
        )
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            if resp.status == 200:
                data = resp.read()
                if len(data) > 200:
                    tile_file.parent.mkdir(parents=True, exist_ok=True)
                    tmp_file = tile_file.with_suffix(".tmp")
                    tmp_file.write_bytes(data)
                    tmp_file.replace(tile_file)
                    return True, "downloaded"
    except Exception as exc:
        return False, str(exc)

    return False, "invalid_response"


def print_cache_status():
    """Print the current cache size and tile count."""
    total_size = 0
    tile_count = 0
    zoom_counts = {}

    if BASEMAP_DIR.exists():
        for root, _, files in os.walk(BASEMAP_DIR):
            for f in files:
                if f.endswith(".png"):
                    tile_count += 1
                    p = Path(root) / f
                    total_size += p.stat().st_size
                    try:
                        rel = p.relative_to(BASEMAP_DIR)
                        z = int(rel.parts[0])
                        zoom_counts[z] = zoom_counts.get(z, 0) + 1
                    except Exception:
                        pass

    print("\n==================================================")
    print("       TERREX OFFLINE SATELLITE TILE CACHE        ")
    print("==================================================")
    print(f"Cache Location : {BASEMAP_DIR}")
    print(f"Total Tiles    : {tile_count:,} tiles")
    print(f"Total Size     : {total_size / (1024 * 1024):.2f} MB")
    print("Zoom Breakdown :")
    for z in sorted(zoom_counts.keys()):
        print(f"  - Zoom {z:2d}: {zoom_counts[z]:5d} tiles")
    if tile_count == 0:
        print("  (Cache is currently empty. Run with --aoi kolkata to populate)")
    print("==================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Download offline satellite basemap tiles for TerreX.")
    parser.add_argument("--aoi", choices=list(PRESET_AOIS.keys()), default=None, help="Preset target region")
    parser.add_argument("--bbox", type=str, default=None, help="Custom bounding box: min_lon,min_lat,max_lon,max_lat")
    parser.add_argument("--zoom-min", type=int, default=None, help="Minimum zoom level (e.g. 8)")
    parser.add_argument("--zoom-max", type=int, default=None, help="Maximum zoom level (e.g. 14)")
    parser.add_argument("--concurrency", type=int, default=8, help="Parallel download worker threads (default: 8)")
    parser.add_argument("--status", action="store_true", help="Display current offline cache statistics")
    args = parser.parse_args()

    if args.status or (not args.aoi and not args.bbox):
        print_cache_status()
        if not args.aoi and not args.bbox:
            print("To download tiles, specify --aoi kolkata or --bbox min_lon,min_lat,max_lon,max_lat")
            return

    # Determine BBox
    if args.aoi:
        preset = PRESET_AOIS[args.aoi]
        min_lon, min_lat, max_lon, max_lat = preset["bbox"]
        z_min = args.zoom_min or preset["default_min_zoom"]
        z_max = args.zoom_max or preset["default_max_zoom"]
        region_name = preset["name"]
    else:
        parts = [float(p.strip()) for p in args.bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("--bbox must contain exactly min_lon,min_lat,max_lon,max_lat")
        min_lon, min_lat, max_lon, max_lat = parts[0], parts[1], parts[2], parts[3]
        z_min = args.zoom_min or 8
        z_max = args.zoom_max or 13
        region_name = f"Custom Bounding Box [{min_lon:.3f}, {min_lat:.3f}, {max_lon:.3f}, {max_lat:.3f}]"

    operational_bounds = (87.75, 21.40, 88.65, 23.60)
    if not (
        operational_bounds[0] <= min_lon < max_lon <= operational_bounds[2]
        and operational_bounds[1] <= min_lat < max_lat <= operational_bounds[3]
    ):
        raise ValueError(
            f"Basemap AOI must stay inside {operational_bounds}; max longitude is 88.65E"
        )

    tiles = calculate_tile_list(min_lon, min_lat, max_lon, max_lat, z_min, z_max)
    total_tiles = len(tiles)

    print(f"\nTarget Region   : {region_name}")
    print(f"Bounding Box    : ({min_lon:.4f}, {min_lat:.4f}) to ({max_lon:.4f}, {max_lat:.4f})")
    print(f"Zoom Range      : {z_min} to {z_max}")
    print(f"Total Tile Grid : {total_tiles:,} tiles across {z_max - z_min + 1} zoom levels")
    print(f"Destination     : {BASEMAP_DIR}\n")

    t0 = time.time()
    downloaded = 0
    cached = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {executor.submit(download_single_tile, z, x, y): (z, x, y) for (z, x, y) in tiles}
        done_count = 0

        for future in as_completed(futures):
            done_count += 1
            ok, status = future.result()
            if ok:
                if status == "downloaded":
                    downloaded += 1
                else:
                    cached += 1
            else:
                failed += 1

            if done_count % 25 == 0 or done_count == total_tiles:
                pct = (done_count / total_tiles) * 100
                sys.stdout.write(
                    f"\r[{done_count:5d}/{total_tiles:5d}] {pct:5.1f}% | "
                    f"Downloaded: {downloaded} | Already Cached: {cached} | Failed: {failed}"
                )
                sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\n\nPre-download complete in {elapsed:.1f}s ({total_tiles/max(1, elapsed):.1f} tiles/sec).")
    print_cache_status()


if __name__ == "__main__":
    main()
