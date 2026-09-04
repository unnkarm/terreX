from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services.discovery import DiscoveryError, ReferenceTileNotFound, discover

logger = logging.getLogger("terrex.api.discovery")
router = APIRouter(prefix="/api/discovery", tags=["discovery"])


@router.get("")
def get_discovery(
    tile_id: Optional[str] = Query(None),
    max_clusters: int = Query(4, ge=1, le=32),
    top_k: int = Query(20, ge=1, le=1000),
):
    try:
        return discover(tile_id=tile_id, max_clusters=max_clusters, top_k=top_k)
    except ReferenceTileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DiscoveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Discovery failed: %s", exc)
        raise HTTPException(status_code=503, detail="Discovery service is unavailable")
