import os
import glob
from pathlib import Path
import rasterio
import sqlite3
import sys
import time

sys.path.insert(0, os.path.abspath("backend"))
from config import settings
from db.database import get_session_factory
from db.models import Scene, Tile

Session = get_session_factory()
session = Session()

# 1. Check existing scenes and tile counts in DB
db_scenes = session.query(Scene).all()
print("=== CURRENT INGESTION PROGRESS ===")
total_done_tiles = 0
for s in db_scenes:
    t_cnt = session.query(Tile).filter(Tile.scene_id == s.scene_id).count()
    total_done_tiles += t_cnt
    print(f"[{s.sensor:10}] Tiles: {t_cnt:5} | Date: {s.acquisition_date} | File: {s.source_filename}")

session.close()

# 2. Check all incoming scenes recursively
tile_size = 256
incoming_files = sorted(
    list(settings.INCOMING_DIR.rglob("*.tif")) + list(settings.INCOMING_DIR.rglob("*.tiff"))
)
print(f"\n=== ALL {len(incoming_files)} INCOMING SCENES ===")
grand_total_est_tiles = 0
scene_info = []

for idx, f in enumerate(incoming_files, 1):
    fname = f.name
    sz_mb = f.stat().st_size / (1024 * 1024)
    with rasterio.open(f) as src:
        w, h, c = src.width, src.height, src.count
        nx = (w + tile_size - 1) // tile_size
        ny = (h + tile_size - 1) // tile_size
        est_grid = nx * ny
        
        # Check if already in DB
        matched_scene = next((s for s in db_scenes if s.source_filename == fname), None)
        status_str = f"DONE ({matched_scene.scene_id[:8]}...)" if matched_scene else "QUEUED"
        
        grand_total_est_tiles += est_grid
        scene_info.append({
            "idx": idx,
            "filename": fname,
            "size_mb": sz_mb,
            "w": w,
            "h": h,
            "bands": c,
            "grid_tiles": est_grid,
            "status": status_str,
            "path": f
        })
        print(f"[{idx}/{len(incoming_files)}] {status_str:15} | {sz_mb:6.1f} MB | {w}x{h} ({c} bands) | ~{est_grid:,} tiles | {fname}")

def get_dir_size(path):
    total = 0
    if not os.path.exists(path):
        return 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except:
                pass
    return total

tiles_bytes = get_dir_size("data/tiles")
db_bytes = os.path.getsize("terrex.db") if os.path.exists("terrex.db") else 0
qdrant_bytes = get_dir_size("data/qdrant_storage")

print("\n=== STORAGE BREAKDOWN ===")
print(f"Raw Input GeoTIFFs (Total 8 scenes): {sum(s['size_mb'] for s in scene_info):.2f} MB ({sum(s['size_mb'] for s in scene_info)/1024:.2f} GB)")
print(f"Current Processed Tiles (PNGs on disk): {tiles_bytes / (1024*1024):.2f} MB")
print(f"Current Metadata Database (terrex.db): {db_bytes / (1024*1024):.2f} MB")
print(f"Current Vector Database (Qdrant): {qdrant_bytes / (1024*1024):.2f} MB")
total_current = (tiles_bytes + db_bytes + qdrant_bytes) / (1024*1024)
print(f"Total Disk Space Consumed by Processed Data: {total_current:.2f} MB ({total_current/1024:.2f} GB)")

if total_done_tiles > 0:
    avg_tile_kb = (tiles_bytes / total_done_tiles) / 1024
    print(f"\nAverage size per tile PNG + embedding: ~{avg_tile_kb:.1f} KB")
    
    # Calculate tiles remaining
    # Note: SAR scenes (scenes 1 & 2) are 20567x25391 (~8100 grid tiles -> ~6435 valid tiles).
    # Optical scenes are Sentinel-2 Level-2A (10980x10980 -> ~1849 tiles per scene).
    # Let's compute accurate estimate:
    # Scene 1: 6435 tiles (Done)
    # Scene 2: 6435 tiles (In progress: currently ~700 tiles)
    # Scenes 3-8: 6 Sentinel-2 scenes @ 10980x10980 -> ~1,849 tiles each = ~11,094 tiles total
    # Total actual tiles = 6435 + 6435 + 11094 = ~23,964 tiles.
    est_total_actual_tiles = 6435 * 2 + (1849 * 6)
    tiles_remaining = max(0, est_total_actual_tiles - total_done_tiles)
    est_remaining_mb = (tiles_remaining * avg_tile_kb) / 1024
    est_total_final_mb = (est_total_actual_tiles * avg_tile_kb) / 1024
    
    print(f"Estimated Total Valid Tiles across all 8 scenes: ~{est_total_actual_tiles:,}")
    print(f"Indexed so far: {total_done_tiles:,} tiles ({total_done_tiles/est_total_actual_tiles*100:.1f}%)")
    print(f"Remaining tiles to process: ~{tiles_remaining:,} tiles")
    print(f"Estimated EXTRA disk space needed: ~{est_remaining_mb:.1f} MB (~{est_remaining_mb/1024:.2f} GB)")
    print(f"Estimated TOTAL processed disk space when 100% complete: ~{est_total_final_mb:.1f} MB (~{est_total_final_mb/1024:.2f} GB)")

