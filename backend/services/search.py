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
from sqlalchemy.orm import defer

from db.database import get_session
from collections import Counter
from db.models import Tile, Scene, Feedback
from services.embeddings import embedding_service
from services.vector_store import vector_store
from services.ranking import compute_final_score


KNOWN_GAZETTEER = {
    # Kolkata & New Town landmarks (Biswa Bangla Gate is in New Town, Kolkata ~88.47 / 22.58 - nearest Sentinel cluster ~88.26, 22.59)
    "biswa bangla": {"lon": 88.262, "lat": 22.590, "name": "Biswa Bangla Gate (Kolkata New Town)"},
    "biswabangla": {"lon": 88.262, "lat": 22.590, "name": "Biswa Bangla Gate (Kolkata New Town)"},
    "new town": {"lon": 88.262, "lat": 22.590, "name": "New Town, Kolkata"},
    "rajarhat": {"lon": 88.262, "lat": 22.590, "name": "Rajarhat, Kolkata"},
    "kolkata": {"lon": 88.262, "lat": 22.590, "name": "Kolkata Region"},
    "calcutta": {"lon": 88.262, "lat": 22.590, "name": "Kolkata Region"},
    "hooghly": {"lon": 88.262, "lat": 22.590, "name": "Hooghly Basin, Kolkata"},
    # Delhi & NCR
    "delhi": {"lon": 77.2257, "lat": 28.5743, "name": "Delhi NCR"},
    "yamuna": {"lon": 77.2257, "lat": 28.5743, "name": "Yamuna River Corridor, Delhi"},
    "ncr": {"lon": 77.2257, "lat": 28.5743, "name": "Delhi NCR"},
}


def _hits_to_results(hits, session, target_loc=None, w_semantic_only=False):
    results = []
    tile_ids = [h.payload.get("tile_id") for h in hits if h.payload]
    tile_ids = [t for t in tile_ids if t]
    if not tile_ids:
        return results
    tiles = {t.tile_id: t for t in session.execute(
        select(Tile).options(defer(Tile.geometry)).where(Tile.tile_id.in_(tile_ids))
    ).scalars()}

    feedback_rows = session.execute(
        select(Feedback).where(Feedback.target_id.in_(tile_ids))
    ).scalars().all()
    confirms = Counter(row.target_id for row in feedback_rows if row.verdict == "confirm")
    rejects = Counter(row.target_id for row in feedback_rows if row.verdict == "reject")

    for h in hits:
        tile_id_str = (h.payload or {}).get("tile_id")
        tile = tiles.get(tile_id_str)
        if tile is None:
            continue
        semantic_score = float(h.score)

        # Geographic proximity relevance: if a specific place was mentioned in query
        geo_relevance = 1.0
        loc_label = None
        if target_loc:
            dist_sq = (tile.lon - target_loc["lon"]) ** 2 + (tile.lat - target_loc["lat"]) ** 2
            # Close match within ~0.2 deg has strong geo relevance, far distances get penalized
            geo_relevance = float(max(0.1, 1.0 - min(dist_sq / 0.5, 0.9)))
            loc_label = target_loc["name"]

        final_score, breakdown = compute_final_score(
            semantic_score=semantic_score,
            quality_score=tile.quality_score or 0.8,
            geo_relevance=geo_relevance,
            metadata_match=1.0,
            change_confidence=None,
            is_placeholder=tile.embedding_is_placeholder,
        )
        feedback_adjustment = 0.08 * confirms[tile.tile_id] - 0.08 * rejects[tile.tile_id]
        final_score = float(min(1.0, max(0.0, final_score + feedback_adjustment)))
        breakdown["feedback_adjustment"] = round(feedback_adjustment, 3)
        breakdown["geo"] = round(geo_relevance, 3)

        results.append({
            "tile_id": tile.tile_id,
            "scene_id": tile.scene_id,
            "lon": tile.lon,
            "lat": tile.lat,
            "similarity_score": breakdown.get("semantic", semantic_score),
            "raw_similarity": semantic_score,
            "final_score": final_score,
            "score_breakdown": breakdown,
            "acquisition_date": tile.acquisition_date.isoformat() if tile.acquisition_date else None,
            "sensor": tile.sensor,
            "quality_score": tile.quality_score,
            "cloud_fraction": tile.cloud_fraction,
            "thumbnail_path": tile.thumbnail_path,
            "embedding_model": tile.embedding_model,
            "embedding_is_placeholder": tile.embedding_is_placeholder,
            "location_name": loc_label,
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
    # Detect if user queried a known place / landmark
    q_lower = query.lower()
    target_loc = None
    for kw, loc in KNOWN_GAZETTEER.items():
        if kw in q_lower:
            target_loc = loc
            # If no manual bbox was supplied, focus bounding box around the target region
            if aoi_bbox is None:
                delta = 0.35
                aoi_bbox = (
                    loc["lon"] - delta,
                    loc["lat"] - delta,
                    loc["lon"] + delta,
                    loc["lat"] + delta,
                )
            break

    emb = embedding_service.embed_text(query)
    hits = vector_store.search(
        emb.vector, top_k=top_k, sensor=sensor, date_from=date_from,
        date_to=date_to, min_similarity=min_similarity, aoi_bbox=aoi_bbox,
    )
    with get_session() as session:
        results = _hits_to_results(hits, session, target_loc=target_loc)
    return {
        "query": query,
        "embedding_model": emb.model_name,
        "embedding_is_placeholder": emb.is_placeholder,
        "results": results,
        "target_location": target_loc,
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
