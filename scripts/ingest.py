"""
CLI: Ingest GeoTIFF/COG satellite imagery from data/incoming/ into TerreX.

Supports:
  - Incremental ingestion (default): only processes newly added files
  - Clean / Reset ingestion (--clean / --reset): wipes Qdrant vector index and DB, then ingests all incoming scenes fresh

Usage:
    python scripts/ingest.py                # Ingest new files incrementally
    python scripts/ingest.py --clean        # Wipe Qdrant & DB, ingest all incoming files fresh
    python scripts/ingest.py --file path/to/file.tif  # Ingest single file
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from config import settings  # noqa: E402
from services.ingestion import ingest_file, IngestionError  # noqa: E402
from services.vector_store import vector_store  # noqa: E402
from db.database import init_db, get_session, get_engine  # noqa: E402
from db.models import Base, Scene  # noqa: E402
from sqlalchemy import select  # noqa: E402


def reset_storage_and_indexes():
    """Wipe Qdrant collection, drop database tables, and clean generated tile caches."""
    print("Resetting TerreX database and vector index...")
    engine = get_engine()

    # 1. Reset Database Tables
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        print("  [db] Database tables reset successfully.")
    except Exception as exc:
        print(f"  [db] Error resetting tables: {exc}")

    # 2. Reset Qdrant Vector Collection
    try:
        if vector_store.client:
            try:
                vector_store.client.delete_collection(vector_store.collection)
                print(f"  [qdrant] Deleted collection '{vector_store.collection}'.")
            except Exception:
                pass
            vector_store._ensure_collection()
            print(f"  [qdrant] Recreated fresh collection '{vector_store.collection}'.")
    except Exception as exc:
        print(f"  [qdrant] Error resetting Qdrant collection: {exc}")

    # 3. Clean generated tiles & scenes cache directories (preserving incoming/)
    for dir_path in [settings.TILES_DIR, settings.SCENES_DIR]:
        if dir_path.exists():
            for item in dir_path.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink(missing_ok=True)
                except Exception:
                    pass
    print("  [cache] Tiles and scenes cache cleaned.")
    print("Reset complete.\n")


def main():
    parser = argparse.ArgumentParser(description="Ingest satellite imagery into TerreX with fast AOI spatial filtering.")
    parser.add_argument("--file", type=str, default=None, help="Ingest a single specific file")
    parser.add_argument("--clean", "--reset", action="store_true", help="Wipe Qdrant & database before ingesting (WARNING: Destructive)")
    parser.add_argument("--aoi", nargs=4, type=float, metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"), default=None, help="Custom AOI bounding box for tile filtering")
    parser.add_argument("--full-swath", action="store_true", help="Disable AOI spatial filter and ingest all tiles across the full scene swath")
    args = parser.parse_args()

    if args.clean:
        reset_storage_and_indexes()
    else:
        init_db()

    # Determine AOI filter configuration
    use_aoi_filter = not args.full_swath
    aoi_bounds = tuple(args.aoi) if args.aoi else None

    if args.file:
        targets = [Path(args.file)]
    else:
        already = set()
        if not args.clean:
            with get_session() as session:
                already = {row[0] for row in session.execute(select(Scene.source_filename))}

        # Recursively find all GeoTIFFs in incoming and subfolders
        all_incoming = sorted(
            list(settings.INCOMING_DIR.rglob("*.tif")) + list(settings.INCOMING_DIR.rglob("*.tiff"))
        )
        targets = [p for p in all_incoming if p.name not in already]

    if not targets:
        print("No new files to ingest in data/incoming/.")
        return

    aoi_desc = "Full Swath (no filter)" if args.full_swath else (f"Custom AOI {aoi_bounds}" if aoi_bounds else f"Greater Kolkata AOI [{settings.INGEST_AOI_MIN_LON}, {settings.INGEST_AOI_MIN_LAT}, {settings.INGEST_AOI_MAX_LON}, {settings.INGEST_AOI_MAX_LAT}]")
    print(f"Ingesting {len(targets)} scene(s) into TerreX (Spatial Mode: {aoi_desc})...\n")
    processed_count = 0
    total_tiles = 0

    for path in targets:
        try:
            result = ingest_file(path, aoi_bounds=aoi_bounds, use_aoi_filter=use_aoi_filter)
            tiles = result.get("created_tiles", result.get("tiles", 0))
            total_tiles += tiles
            processed_count += 1
            print(
                f"[OK]  {path.name}\n"
                f"      -> Scene ID: {result['scene_id']}\n"
                f"      -> Sensor: {result.get('sensor', 'unknown')}, Date: {result.get('acquisition_date', 'unknown')}\n"
                f"      -> Tiles: {tiles} cut, Avg Quality: {result.get('quality_score', 0):.2f}\n"
                f"      -> Model: {result.get('embedding_model', 'unknown')} (took {result.get('elapsed_seconds', 0)}s)\n"
            )
        except IngestionError as exc:
            print(f"[FAIL] {path.name}: {exc}\n")

    print(
        f"Ingestion Finished: {processed_count}/{len(targets)} scenes ingested, "
        f"{total_tiles} total tiles indexed in Qdrant."
    )


if __name__ == "__main__":
    main()
