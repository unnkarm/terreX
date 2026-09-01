"""
Rebuilds the Qdrant vector index from tiles already recorded in PostgreSQL,
by re-embedding each tile's saved thumbnail. This is a *recovery* tool
(e.g. after wiping Qdrant, or after swapping in real RemoteCLIP weights and
wanting fresh embeddings for existing tiles) — normal day-to-day ingestion
of new imagery does NOT require running this (see scripts/ingest.py, which
adds to the existing index incrementally).

Usage:
    python scripts/build_index.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

from db.database import init_db, get_session  # noqa: E402
from db.models import Tile  # noqa: E402
from services.embeddings import embedding_service  # noqa: E402
from services.vector_store import vector_store  # noqa: E402


def main():
    init_db()
    with get_session() as session:
        tiles = session.execute(select(Tile)).scalars().all()
        print(f"Re-embedding {len(tiles)} tiles...")
        for t in tiles:
            img = Image.open(t.tile_path)
            emb = embedding_service.embed_image(img)
            vector_store.upsert_tile(
                tile_id=t.tile_id,
                vector=emb.vector,
                payload={
                    "scene_id": t.scene_id,
                    "lon": t.lon,
                    "lat": t.lat,
                    "sensor": t.sensor,
                    "acquisition_date": t.acquisition_date.isoformat() if t.acquisition_date else None,
                    "quality_score": t.quality_score,
                    "cloud_fraction": t.cloud_fraction,
                    "thumbnail_path": t.thumbnail_path,
                    "embedding_is_placeholder": emb.is_placeholder,
                },
            )
            t.embedding_model = emb.model_name
            t.embedding_is_placeholder = emb.is_placeholder
        print("Done.")


if __name__ == "__main__":
    main()
