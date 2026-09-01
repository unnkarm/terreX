"""
CLI: ingest new GeoTIFF/COG files from data/incoming/ incrementally.

Usage (inside backend container / venv with PYTHONPATH=backend):
    python scripts/ingest.py
    python scripts/ingest.py --file data/incoming/SensorA_20230101_demoAOI.tif
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from config import settings  # noqa: E402
from services.ingestion import ingest_file, IngestionError  # noqa: E402
from db.database import init_db, get_session  # noqa: E402
from db.models import Scene  # noqa: E402
from sqlalchemy import select  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default=None, help="Ingest a single specific file")
    args = parser.parse_args()

    init_db()

    if args.file:
        targets = [Path(args.file)]
    else:
        with get_session() as session:
            already = {row[0] for row in session.execute(select(Scene.source_filename))}
        targets = [
            p for p in list(settings.INCOMING_DIR.glob("*.tif")) + list(settings.INCOMING_DIR.glob("*.tiff"))
            if p.name not in already
        ]

    if not targets:
        print("No new files to ingest.")
        return

    for path in targets:
        try:
            result = ingest_file(path)
            print(f"OK  {path.name} -> scene {result['scene_id']} ({result['tiles']} tiles, "
                  f"quality={result['quality_score']:.2f}, embedding={result['embedding_model']}"
                  f"{' [PLACEHOLDER]' if result['embedding_is_placeholder'] else ''})")
        except IngestionError as exc:
            print(f"FAIL {path.name}: {exc}")


if __name__ == "__main__":
    main()
