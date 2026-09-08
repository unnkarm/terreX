from __future__ import annotations

from fastapi import APIRouter

from config import settings
from services.embeddings import embedding_service
from services.prithvi import prithvi_service
from services.chat_agent import chat_status, maybe_unload_llm
from services.vector_store import vector_store
from services.capabilities import CAPABILITIES
from db.database import get_session
from db.models import Tile
from sqlalchemy import select

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def status():
    """
    Surfaces whether real models are staged or the pipeline is running on
    honest placeholders — shown in the UI so an analyst always knows what
    kind of result they're looking at (per offline + no-fake-AI constraints).
    """
    maybe_unload_llm()
    vector_index_count = vector_store.count()
    with get_session() as session:
        stored_versions = sorted({v for v in session.execute(select(Tile.embedding_model_version)).scalars().all() if v})
    current_embedding_version = embedding_service.model_version
    embedding_version_warning = bool(stored_versions and current_embedding_version not in stored_versions)
    chat = chat_status()
    return {
        "offline_mode": settings.OFFLINE_MODE,
        "processing_version": settings.PROCESSING_VERSION,
        "models": {
            "remoteclip": {
                "staged": not embedding_service.is_placeholder,
                "active_model": (
                    embedding_service._real.model_name if not embedding_service.is_placeholder
                    else embedding_service._placeholder.model_name
                ),
            },
            "prithvi": {
                "staged": not prithvi_service.is_placeholder,
                "active_model": (
                    prithvi_service._real.model_name if not prithvi_service.is_placeholder
                    else prithvi_service._placeholder.model_name
                ),
            },
        },
        "paths": {
            "model_dir": str(settings.MODEL_DIR),
            "data_dir": str(settings.DATA_DIR),
        },
        "chat_available": chat["available"],
        "chat": chat,
        "vector_index_count": vector_index_count,
        "vector_index_empty": vector_index_count == 0,
        "embedding_model_version": current_embedding_version,
        "stored_embedding_model_versions": stored_versions,
        "embedding_version_warning": embedding_version_warning,
        "capabilities": CAPABILITIES,
    }
