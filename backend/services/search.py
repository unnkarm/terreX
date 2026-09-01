"""
Feature 2 — Semantic (text) search
Feature 3 — Image-to-image search

Both funnel through the same path: embed query -> Qdrant ANN search ->
PostGIS metadata join/filter -> hybrid ranking.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PIL import Image
from sqlalchemy import select

from db.database import get_session
from db.models import Tile, Scene
from services.embeddings import embedding_service
from services.vector_store import vector_store
from services.ranking import compute_final_score


def _hits_to_results(hits, session, w_semantic_only=False):
    results = []
    tile_ids = [h.id for h in hits]
    if not tile_ids:
        return results
    tiles = {t.tile_id: t for t in session.execute(
        select(Tile).where(Tile.tile_id.in_(tile_ids))
    ).scalars()}
    for h in hits:
        tile = tiles.get(h.id)
        if tile is None:
            continue
        semantic_score = float(h.score)
        final_score, breakdown = compute_final_score(
            semantic_score=semantic_score,
            quality_score=tile.quality_score or 0.5,
            geo_relevance=1.0,   # no AOI centroid distance requested -> neutral
            metadata_match=1.0,  # filters already applied at query time
            change_confidence=None,
        )
        results.append({
            "tile_id": tile.tile_id,
            "scene_id": tile.scene_id,
            "lon": tile.lon,
            "lat": tile.lat,
            "similarity_score": semantic_score,
            "final_score": final_score,
            "score_breakdown": breakdown,
            "acquisition_date": tile.acquisition_date.isoformat() if tile.acquisition_date else None,
            "sensor": tile.sensor,
            "quality_score": tile.quality_score,
            "cloud_fraction": tile.cloud_fraction,
            "thumbnail_path": tile.thumbnail_path,
            "embedding_model": tile.embedding_model,
            "embedding_is_placeholder": tile.embedding_is_placeholder,
        })
    results.sort(key=lambda r: r["final_score"], reverse=True)
    return results


def semantic_text_search(
    query: str,
    top_k: int = 20,
    sensor: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_similarity: float = 0.0,
    aoi_bbox: Optional[tuple] = None,
):
    emb = embedding_service.embed_text(query)
    hits = vector_store.search(
        emb.vector, top_k=top_k, sensor=sensor, date_from=date_from,
        date_to=date_to, min_similarity=min_similarity, aoi_bbox=aoi_bbox,
    )
    with get_session() as session:
        results = _hits_to_results(hits, session)
    return {
        "query": query,
        "embedding_model": emb.model_name,
        "embedding_is_placeholder": emb.is_placeholder,
        "results": results,
    }


def image_to_image_search(
    image: Image.Image,
    top_k: int = 20,
    sensor: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_similarity: float = 0.0,
    aoi_bbox: Optional[tuple] = None,
):
    emb = embedding_service.embed_image(image)
    hits = vector_store.search(
        emb.vector, top_k=top_k, sensor=sensor, date_from=date_from,
        date_to=date_to, min_similarity=min_similarity, aoi_bbox=aoi_bbox,
    )
    with get_session() as session:
        results = _hits_to_results(hits, session)
    return {
        "embedding_model": emb.model_name,
        "embedding_is_placeholder": emb.is_placeholder,
        "results": results,
    }
