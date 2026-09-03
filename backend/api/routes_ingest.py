from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy import select

from config import settings
from db.database import get_db, get_session
from db.models import Scene
from services.ingestion import ingest_file, IngestionError
from services.vector_store import vector_store
from fastapi import Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


@router.post("/upload")
async def upload_and_ingest(file: UploadFile = File(...)):
    """Upload a GeoTIFF/COG directly and ingest it immediately."""
    dest = settings.INCOMING_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = ingest_file(dest)
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


@router.post("/process-incoming")
def process_incoming():
    """
    Scan data/incoming/ for any *.tif/*.tiff not yet in the scenes table and
    ingest them independently — supports incremental indexing (Feature 9)
    without a full rebuild.
    """
    started = time.perf_counter()
    processed, skipped, failed = [], [], []
    for path in list(settings.INCOMING_DIR.glob("*.tif")) + list(settings.INCOMING_DIR.glob("*.tiff")):
        try:
            result = ingest_file(path)
            (skipped if result.get("status") == "skipped" else processed).append(result)
        except IngestionError as exc:
            failed.append({"file": path.name, "error": str(exc)})
    return {
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "metrics": {
            "scenes_processed": len(processed),
            "scenes_skipped": len(skipped),
            "scenes_failed": len(failed),
            "tiles_created": sum(r.get("created_tiles", r.get("tiles", 0)) for r in processed),
            "tiles_skipped": sum(r.get("skipped_tiles", 0) for r in processed + skipped),
            "tiles_discarded": sum(r.get("discarded_tiles", 0) for r in processed),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "vector_index_count": vector_store.count(),
        },
    }


@router.get("/scenes")
def list_scenes(db: Session = Depends(get_db)):
    scenes = db.execute(select(Scene)).scalars().all()
    return [
        {
            "scene_id": s.scene_id,
            "source_filename": s.source_filename,
            "sensor": s.sensor,
            "acquisition_date": s.acquisition_date.isoformat() if s.acquisition_date else None,
            "quality_score": s.quality_score,
            "cloud_fraction": s.cloud_fraction,
            "status": s.status,
            "status_reason": s.status_reason,
            "source_hash": s.source_hash,
            "license_source": s.license_source,
            "cog_validation": s.cog_validation,
            "processing_version": s.processing_version,
            "tile_count": len(s.tiles),
        }
        for s in scenes
    ]
