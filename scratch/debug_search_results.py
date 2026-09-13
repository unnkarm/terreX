import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.search import semantic_text_search
from services.vector_store import vector_store
from services.embeddings import embedding_service
from services.nlp_filter import compute_distance_km
from db.database import get_session
from db.models import Tile, Scene
from sqlalchemy import select

q = "water bodies and rivers within 5km of Biswa Bangla Gate with clear sky"
print(f"Testing search for: '{q}'\n")

res = semantic_text_search(q, top_k=20, sensor="Sentinel-2", min_similarity=0.0)
print(f"Total Results: {len(res.get('results', []))}")
print(f"Parsed Filters: {json.dumps(res.get('parsed_filters', {}), indent=2)}")

# Check vector store raw hits
emb = embedding_service.embed_text("water bodies and rivers")
raw_hits = vector_store.search(emb.vector, top_k=20, sensor="Sentinel-2", min_similarity=0.0)
print(f"\nRaw Vector Store Hits: {len(raw_hits)}")

with get_session() as session:
    tiles = session.execute(select(Tile).limit(10)).scalars().all()
    print(f"\nSample indexed tiles in DB: {len(tiles)}")
    for t in tiles[:5]:
        d_km = compute_distance_km(t.lon, t.lat, "Biswa Bangla Gate")
        print(f"  Tile {t.tile_id[:8]}: ({t.lon:.4f}, {t.lat:.4f}), sensor={t.sensor}, cloud={t.cloud_fraction}, dist_to_BBG={d_km:.2f} km" if d_km else f"  Tile {t.tile_id[:8]}: dist_to_BBG=None")
