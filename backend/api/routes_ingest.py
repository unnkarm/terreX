from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Body
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from config import settings
from db.database import get_db, get_session
from db.models import Scene, Tile
from services.ingestion import ingest_file, IngestionError
from data_sources import list_available_sources, get_data_source
from services.vector_store import vector_store
from services.ingestion import _load_provenance


router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


class ProviderSearchRequest(BaseModel):
    provider: str = "sentinel2"  # "sentinel2" | "isro-bhuvan" | "isro-mosdac"
    bbox: List[float] = [88.25, 22.45, 88.48, 22.65]  # Default: Kolkata AOI
    start_date: str = "2023-01-01"
    end_date: str = "2026-01-01"
    max_cloud_cover: float = 15.0
    limit: int = 6


class ProviderStageRequest(BaseModel):
    provider: str
    item_id: str
    target_bbox: Optional[List[float]] = None


@router.get("/sources")
def get_sources():
    """Returns registered EO providers: Sentinel-2 (Primary ML), ISRO Bhuvan, ISRO MOSDAC."""
    return list_available_sources()


@router.post("/search-provider")
def search_provider(req: ProviderSearchRequest = Body(...)):
    """Search provider catalog (Sentinel-2, ISRO Bhuvan, ISRO MOSDAC) by AOI and date range."""
    src = get_data_source(req.provider)
    if not src:
        raise HTTPException(status_code=400, detail=f"Unknown data source provider: '{req.provider}'")

    results = src.search(
        bbox_wgs84=req.bbox,
        start_date=req.start_date,
        end_date=req.end_date,
        max_cloud_cover=req.max_cloud_cover,
        limit=req.limit,
    )

    return {
        "provider": src.provider_id,
        "provider_name": src.provider_name,
        "count": len(results),
        "results": [
            {
                "item_id": r.item_id,
                "dataset_name": r.dataset_name,
                "acquisition_date": r.acquisition_date.isoformat(),
                "cloud_cover_percent": r.cloud_cover_percent,
                "bbox": r.bbox_wgs84,
                "spatial_resolution_m": r.spatial_resolution_m,
                "bands": r.bands,
                "metadata": r.metadata,
            }
            for r in results
        ],
    }


@router.post("/stage-provider")
def stage_provider_scene(req: ProviderStageRequest = Body(...)):
    """Stage a scene from Sentinel-2 or ISRO archive into data/incoming/ for TerreX ingestion."""
    src = get_data_source(req.provider)
    if not src:
        raise HTTPException(status_code=400, detail=f"Unknown data source provider: '{req.provider}'")

    # Locate item in search catalog
    items = src.search(
        bbox_wgs84=req.target_bbox or [88.25, 22.45, 88.48, 22.65],
        start_date="2020-01-01",
        end_date="2026-12-31",
        limit=50,
    )
    target = next((i for i in items if i.item_id == req.item_id), None)
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Provider item '{req.item_id}' was not found in the local catalog",
        )

    staged_path = src.stage_to_cog(target, settings.INCOMING_DIR, req.target_bbox)
    return {
        "status": "staged",
        "provider": req.provider,
        "item_id": req.item_id,
        "staged_path": str(staged_path),
        "message": f"Scene {req.item_id} staged into {staged_path.name}. Ready for TerreX tiling & embedding.",
    }


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
    ingest them independently — supports incremental indexing without a full rebuild.
    """
    started = time.perf_counter()
    provenance_errors = []
    for candidate in list(settings.INCOMING_DIR.rglob("*.tif")) + list(settings.INCOMING_DIR.rglob("*.tiff")):
        try:
            _load_provenance(candidate)
        except IngestionError as exc:
            provenance_errors.append({"file": candidate.name, "error": str(exc)})
    if provenance_errors:
        raise HTTPException(status_code=422, detail={"message": "Incoming imagery failed provenance pre-check", "files": provenance_errors})
    processed, skipped, failed = [], [], []
    for path in list(settings.INCOMING_DIR.rglob("*.tif")) + list(settings.INCOMING_DIR.rglob("*.tiff")):
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
    tile_counts = dict(
        db.execute(
            select(Tile.scene_id, func.count(Tile.tile_id)).group_by(Tile.scene_id)
        ).all()
    )
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
            "source_portal": s.source_portal,
            "underlying_dataset": s.underlying_dataset,
            "cloud_cover_pct": s.cloud_cover_pct,
            "provenance": s.provenance,
            "cog_validation": s.cog_validation,
            "processing_version": s.processing_version,
            "tile_count": tile_counts.get(s.scene_id, 0),
        }
        for s in scenes
    ]


@router.get("/stats")
def get_ingest_stats(db: Session = Depends(get_db)):
    """Return live ingestion statistics, vector count, and disk telemetry."""
    v_count = vector_store.count()
    scenes = db.execute(select(Scene)).scalars().all()
    tile_counts = dict(
        db.execute(
            select(Tile.scene_id, func.count(Tile.tile_id)).group_by(Tile.scene_id)
        ).all()
    )
    incoming_files = [p.name for p in settings.INCOMING_DIR.rglob("*.tif")] + [p.name for p in settings.INCOMING_DIR.rglob("*.tiff")]
    
    # Calculate tile counts from disk
    tiles_on_disk = len(list(settings.TILES_DIR.rglob("*.png")))

    scene_items = [
        {
            "scene_id": s.scene_id,
            "source_filename": s.source_filename,
            "sensor": s.sensor,
            "acquisition_date": s.acquisition_date.isoformat() if s.acquisition_date else None,
            "quality_score": s.quality_score,
            "cloud_fraction": s.cloud_fraction,
            "tile_count": tile_counts.get(s.scene_id, 0),
        }
        for s in scenes
    ]
    
    return {
        "vector_count": v_count,
        "scenes_count": len(scenes),
        "scenes": scene_items,
        "tiles_on_disk": tiles_on_disk,
        "incoming_count": len(incoming_files),
        "incoming_files": incoming_files,
        "active_modalities": ["Sentinel-2 L2A (Optical VNIR/SWIR)", "Sentinel-1 GRD (SAR Radar)", "Landsat 8/9 C2L2", "ISRO Resourcesat"],
        "is_incremental": True,
    }

