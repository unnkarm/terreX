from __future__ import annotations

import os
import logging

# Enforce offline variables before importing torch/transformers/rasterio
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("PROJ_NETWORK", "OFF")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from db.database import init_db
from api import routes_search, routes_ingest, routes_change, routes_feedback, routes_system, routes_chat, routes_discovery, routes_review
from services.chat_agent import start_idle_unload_monitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("terrex")

app = FastAPI(
    title="TerreX — Offline AI Satellite Intelligence Platform",
    version=settings.PROCESSING_VERSION,
    description=(
        "Offline satellite imagery search & change-detection API. "
        "OFFLINE_MODE={}".format(settings.OFFLINE_MODE)
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve tile thumbnails / change masks / source data read-only, so the
# frontend can render imagery directly (fully offline, no external CDN).
app.mount("/static", StaticFiles(directory=str(settings.DATA_DIR)), name="static")

app.include_router(routes_search.router)
app.include_router(routes_ingest.router)
app.include_router(routes_change.router)
app.include_router(routes_feedback.router)
app.include_router(routes_system.router)
app.include_router(routes_chat.router)
app.include_router(routes_discovery.router)
app.include_router(routes_review.router)


@app.on_event("startup")
def on_startup():
    if settings.OFFLINE_MODE:
        assert os.environ.get("HF_HUB_OFFLINE") == "1", "HF_HUB_OFFLINE guard failed"
        assert os.environ.get("TRANSFORMERS_OFFLINE") == "1", "TRANSFORMERS_OFFLINE guard failed"
        assert os.environ.get("PROJ_NETWORK") == "OFF", "PROJ_NETWORK guard failed"
        logger.info("OFFLINE_MODE verified — strict air-gap guards active (HF, Transformers, PROJ).")

    init_db()
    start_idle_unload_monitor()

    # Automatically pre-load Sentinel granules if the database has no scenes yet
    try:
        from db.database import get_session
        from db.models import Scene
        from sqlalchemy import select, func
        with get_session() as session:
            count = session.scalar(select(func.count(Scene.scene_id))) or 0
        if count == 0:
            logger.info("Database empty on startup. Auto-ingesting Sentinel granules from data/incoming...")
            from services.ingestion import ingest_file
            targets = list(settings.INCOMING_DIR.glob("*.tif")) + list(settings.INCOMING_DIR.glob("*.tiff"))
            for path in targets:
                try:
                    res = ingest_file(path)
                    logger.info("Auto-ingested %s (scene %s, %d tiles)", path.name, res["scene_id"], res["tiles"])
                except Exception as exc:
                    logger.warning("Auto-ingest skipped %s: %s", path.name, exc)
    except Exception as exc:
        logger.warning("Startup scene auto-ingest check error: %s", exc)

    logger.info("TerreX backend ready. Model dir=%s Data dir=%s", settings.MODEL_DIR, settings.DATA_DIR)


@app.get("/")
def root():
    return {"service": "terrex-backend", "status": "ok", "offline_mode": settings.OFFLINE_MODE}


@app.get("/health")
def health():
    return {"status": "healthy"}
