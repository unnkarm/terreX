from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Body
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from db.database import get_db, get_session
from db.models import Scene
from services.ingestion import ingest_file, IngestionError
from data_sources import list_available_sources, get_data_source

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
        # Fallback dummy for immediate staging response
        from data_sources.base import EOSearchResult
        from datetime import datetime
        target = EOSearchResult(
            item_id=req.item_id,
            provider=req.provider,
            dataset_name="Staged EO Scene",
            acquisition_date=datetime.utcnow(),
            cloud_cover_percent=2.0,
            bbox_wgs84=req.target_bbox or [88.25, 22.45, 88.48, 22.65],
            spatial_resolution_m=10.0,
            bands=["B02", "B03", "B04", "B08"],
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
    with get_session() as session:
        already = {row[0] for row in session.execute(select(Scene.source_filename))}

    processed, failed = [], []
    for path in list(settings.INCOMING_DIR.glob("*.tif")) + list(settings.INCOMING_DIR.glob("*.tiff")):
        if path.name in already:
            continue
        try:
            processed.append(ingest_file(path))
        except IngestionError as exc:
            failed.append({"file": path.name, "error": str(exc)})
    return {"processed": processed, "failed": failed}


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
            "processing_version": s.processing_version,
            "tile_count": len(s.tiles),
        }
        for s in scenes
    ]
