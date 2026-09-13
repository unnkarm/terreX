import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from db.database import get_session
from db.models import Scene, Tile
from sqlalchemy import select, func

with get_session() as session:
    scenes = session.execute(select(Scene)).scalars().all()
    print(f"Total Scenes in DB: {len(scenes)}")
    for s in scenes:
        tile_count = session.execute(select(func.count(Tile.tile_id)).where(Tile.scene_id == s.scene_id)).scalar()
        print(f"  Scene: {s.source_filename}")
        print(f"    Sensor: {s.sensor} | Portal: {s.source_portal} | Cloud: {s.cloud_cover_pct}% | Indexed Tiles: {tile_count}")
