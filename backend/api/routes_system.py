from __future__ import annotations

from fastapi import APIRouter

from config import settings
from services.embeddings import embedding_service
from services.prithvi import prithvi_service

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def status():
    """
    Surfaces whether real models are staged or the pipeline is running on
    honest placeholders — shown in the UI so an analyst always knows what
    kind of result they're looking at (per offline + no-fake-AI constraints).
    """
    return {
        "offline_mode": settings.OFFLINE_MODE,
        "processing_version": settings.PROCESSING_VERSION,
        "models": {
            "remoteclip": {
                "staged": not embedding_service.is_placeholder,
                "active_model": (
                    "remoteclip" if not embedding_service.is_placeholder
                    else embedding_service._placeholder.model_name
                ),
            },
            "prithvi": {
                "staged": not prithvi_service.is_placeholder,
                "active_model": (
                    "prithvi-eo-v1" if not prithvi_service.is_placeholder
                    else prithvi_service._placeholder.model_name
                ),
            },
        },
        "paths": {
            "model_dir": str(settings.MODEL_DIR),
            "data_dir": str(settings.DATA_DIR),
        },
    }
