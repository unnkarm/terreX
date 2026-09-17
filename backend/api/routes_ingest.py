from __future__ import annotations

import shutil
import threading
import time
import uuid
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
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _run_incoming_job(job_id: str, paths: list[Path]) -> None:
    def update(phase: str, completed: int, total: int) -> None:
        with _jobs_lock:
            job = _jobs[job_id]
            job["phase"] = phase
            job["stage_progress"][phase] = round(100 * completed / max(total, 1))
            job["message"] = f"{phase.title()}: {completed}/{total} windows"

    processed, skipped, failed = [], [], []
    for position, path in enumerate(paths, start=1):
        with _jobs_lock:
            job = _jobs[job_id]
            job.update({"current_file": path.name, "scene_position": position, "message": f"Validating scene {position}/{len(paths)}: {path.name}"})
            job["stage_progress"]["validation"] = 100
            job["stage_progress"]["georeference"] = 100
        try:
            result = ingest_file(path, progress=update)
            (skipped if result.get("status") == "skipped" else processed).append(result)
        except Exception as exc:
            failed.append({"file": path.name, "error": str(exc)})
    with _jobs_lock:
        job = _jobs[job_id]
        job.update({"status": "complete", "phase": "indexing", "message": "Qdrant and SQLite indexes updated", "processed": processed, "skipped": skipped, "failed": failed})
        job["stage_progress"].update({"tiling": 100, "quality": 100, "embedding": 100, "indexing": 100})


def _assert_operational_bbox(bbox: List[float]) -> None:
    bounds = (
        settings.KOLKATA_AOI_MIN_LON,
        settings.KOLKATA_AOI_MIN_LAT,
        settings.KOLKATA_AOI_MAX_LON,
        settings.KOLKATA_AOI_MAX_LAT,
    )
    if len(bbox) != 4 or not (
        bounds[0] <= bbox[0] < bbox[2] <= bounds[2]
        and bounds[1] <= bbox[1] < bbox[3] <= bounds[3]
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Provider AOI must stay inside {bounds}; max longitude is {bounds[2]:.2f}E",
        )


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
    _assert_operational_bbox(req.bbox)
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

    target_bbox = req.target_bbox or [88.25, 22.45, 88.48, 22.65]
    _assert_operational_bbox(target_bbox)
    # Locate item in search catalog
    items = src.search(
        bbox_wgs84=target_bbox,
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

    staged_path = src.stage_to_cog(target, settings.INCOMING_DIR, target_bbox)
    return {
        "status": "staged",
        "provider": req.provider,
        "item_id": req.item_id,
        "staged_path": str(staged_path),
        "message": f"Scene {req.item_id} staged into {staged_path.name}. Ready for TerreX tiling & embedding.",
    }


@router.post("/upload")
async def upload_and_ingest(
    file: UploadFile = File(...),
    provenance: UploadFile = File(...),
):
    """Upload a GeoTIFF/COG and its mandatory provenance JSON sidecar."""
    safe_name = Path(file.filename or "").name
    if not safe_name or Path(safe_name).suffix.lower() not in {".tif", ".tiff"}:
        raise HTTPException(status_code=422, detail="A .tif or .tiff raster is required")
    expected_sidecar = f"{Path(safe_name).stem}.provenance.json"
    if Path(provenance.filename or "").name != expected_sidecar:
        raise HTTPException(
            status_code=422,
            detail=f"Provenance filename must be {expected_sidecar}",
        )
    settings.INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    dest = settings.INCOMING_DIR / safe_name
    sidecar_dest = settings.INCOMING_DIR / expected_sidecar
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    with open(sidecar_dest, "wb") as f:
        shutil.copyfileobj(provenance.file, f)
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
    provenance_errors = []
    for candidate in list(settings.INCOMING_DIR.rglob("*.tif")) + list(settings.INCOMING_DIR.rglob("*.tiff")):
        try:
            _load_provenance(candidate)
        except IngestionError as exc:
            provenance_errors.append({"file": candidate.name, "error": str(exc)})
    if provenance_errors:
        raise HTTPException(status_code=422, detail={"message": "Incoming imagery failed provenance pre-check", "files": provenance_errors})
    paths = list(settings.INCOMING_DIR.rglob("*.tif")) + list(settings.INCOMING_DIR.rglob("*.tiff"))
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"job_id": job_id, "status": "running", "phase": "validation", "message": "Queued", "current_file": None, "scene_position": 0, "scene_total": len(paths), "stage_progress": {"validation": 0, "georeference": 0, "tiling": 0, "quality": 0, "embedding": 0, "indexing": 0}, "processed": [], "skipped": [], "failed": []}
    threading.Thread(target=_run_incoming_job, args=(job_id, paths), daemon=True).start()
    return {"job_id": job_id, "status": "running"}


@router.get("/jobs/{job_id}")
def get_ingestion_job(job_id: str):
    """Live progress for a user-triggered incoming-directory ingestion job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        return dict(job)


@router.get("/scenes")
def list_scenes(
    status: Optional[str] = "ingested",
    include_empty: bool = False,
    db: Session = Depends(get_db),
):
    stmt = select(Scene)
    if status and status.lower() != "all":
        stmt = stmt.where(Scene.status == status)
    scenes = db.execute(stmt).scalars().all()
    tile_counts = dict(
        db.execute(
            select(Tile.scene_id, func.count(Tile.tile_id)).group_by(Tile.scene_id)
        ).all()
    )
    results = [
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
    if not include_empty:
        results = [r for r in results if r["tile_count"] > 0]
    return results


@router.get("/stats")
def get_ingest_stats(db: Session = Depends(get_db)):
    """Return live ingestion statistics, vector count, and disk telemetry."""
    v_count = vector_store.count()
    scenes = db.execute(select(Scene).where(Scene.status == "ingested")).scalars().all()
    quarantined_count = db.scalar(select(func.count(Scene.scene_id)).where(Scene.status == "quarantined")) or 0
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
        "quarantined_count": quarantined_count,
        "scenes": scene_items,
        "tiles_on_disk": tiles_on_disk,
        "incoming_count": len(incoming_files),
        "incoming_files": incoming_files,
        "active_modalities": ["Sentinel-2 L2A (Optical VNIR/SWIR)", "Sentinel-1 GRD (SAR Radar)", "Landsat 8/9 C2L2", "ISRO Resourcesat"],
        "is_incremental": True,
    }
