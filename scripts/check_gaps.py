import glob, os, re, sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from db.database import get_session, init_db
from db.models import Scene
from sqlalchemy import select

init_db()

# 1. Fetch DB scenes
with get_session() as db:
    db_scenes = db.execute(select(Scene)).scalars().all()
    print(f"=== SCENES CURRENTLY IN DATABASE ({len(db_scenes)} scenes) ===")
    
    s1_db = [s for s in db_scenes if s.sensor in ('SAR-C', 'Sentinel-1', 'SAR')]
    s2_db = [s for s in db_scenes if s.sensor in ('MSI', 'Sentinel-2', 'Optical')]
    
    s1_db.sort(key=lambda s: s.acquisition_date if s.acquisition_date else datetime.min)
    s2_db.sort(key=lambda s: s.acquisition_date if s.acquisition_date else datetime.min)
    
    print("\n--- Sentinel-1 SAR in DB ---")
    for i, s in enumerate(s1_db):
        gap_str = "Baseline"
        if i > 0 and s.acquisition_date and s1_db[i-1].acquisition_date:
            days = (s.acquisition_date - s1_db[i-1].acquisition_date).total_seconds() / 86400.0
            gap_str = f"Gap: {days:.1f}d"
        dt_str = s.acquisition_date.strftime('%Y-%m-%d') if s.acquisition_date else 'Unknown'
        print(f"[{i+1:02d}] {dt_str} | {gap_str:<12} | {s.source_filename[:50]}")
        
    print("\n--- Sentinel-2 Optical in DB ---")
    for i, s in enumerate(s2_db):
        gap_str = "Baseline"
        if i > 0 and s.acquisition_date and s2_db[i-1].acquisition_date:
            days = (s.acquisition_date - s2_db[i-1].acquisition_date).total_seconds() / 86400.0
            gap_str = f"Gap: {days:.1f}d"
        dt_str = s.acquisition_date.strftime('%Y-%m-%d') if s.acquisition_date else 'Unknown'
        print(f"[{i+1:02d}] {dt_str} | {gap_str:<12} | {s.source_filename[:50]}")

# 2. Check ALL files in data/incoming and data/scenes
all_tif_files = glob.glob('data/**/*.tif', recursive=True)
s1_files = []
s2_files = []

for f in all_tif_files:
    fname = os.path.basename(f)
    m1 = re.search(r'S1[A-D]_IW_GRDH_1S.._(\d{8})T(\d{6})', fname)
    if m1:
        dt = datetime.strptime(m1.group(1) + m1.group(2), '%Y%m%d%H%M%S')
        s1_files.append((dt, fname, f))
    m2 = re.search(r'S2[A-D]_MSIL\w+_(\d{8})T(\d{6})', fname)
    if m2:
        dt = datetime.strptime(m2.group(1) + m2.group(2), '%Y%m%d%H%M%S')
        s2_files.append((dt, fname, f))

s1_files = sorted({x[1]: x for x in s1_files}.values(), key=lambda x: x[0])
s2_files = sorted({x[1]: x for x in s2_files}.values(), key=lambda x: x[0])

print(f"\n=======================================================")
print(f"=== ALL UNIQUE SCENES ON DISK (INGESTED + INCOMING) ===")
print(f"=======================================================")

print(f"\n>>> Sentinel-1 SAR Total: {len(s1_files)} scenes")
for i, (dt, fname, fpath) in enumerate(s1_files):
    gap_str = "Baseline"
    if i > 0:
        days = (dt - s1_files[i-1][0]).total_seconds() / 86400.0
        gap_str = f"Gap: {days:.1f}d"
    print(f"[{i+1:02d}] {dt.strftime('%Y-%m-%d %H:%M')} | {gap_str:<14} | {fname}")

print(f"\n>>> Sentinel-2 Optical Total: {len(s2_files)} scenes")
for i, (dt, fname, fpath) in enumerate(s2_files):
    gap_str = "Baseline"
    if i > 0:
        days = (dt - s2_files[i-1][0]).total_seconds() / 86400.0
        gap_str = f"Gap: {days:.1f}d"
    print(f"[{i+1:02d}] {dt.strftime('%Y-%m-%d %H:%M')} | {gap_str:<14} | {fname}")
