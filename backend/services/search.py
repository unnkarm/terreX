"""
Feature 2 — Semantic (text) search
Feature 3 — Image-to-image search

Both funnel through the same path: embed query -> Qdrant ANN search ->
PostGIS metadata join/filter -> hybrid ranking.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Any, Dict

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import defer

from db.database import get_session
from collections import Counter
from db.models import Tile, Scene, Feedback
from services.embeddings import embedding_service
from services.vector_store import vector_store
from services.ranking import compute_final_score
from services.nlp_filter import parse_natural_language_query, compute_distance_km, ParsedQueryFilters
from shapely.geometry import Point, Polygon, shape

KNOWN_GAZETTEER: Dict[str, Dict[str, Any]] = {
    "kolkata": {"name": "Kolkata (Hooghly Basin)", "lon": 88.3639, "lat": 22.5726},
    "delhi": {"name": "Delhi NCR (Yamuna Basin)", "lon": 77.2090, "lat": 28.6139},
    "hooghly": {"name": "Hooghly River Basin", "lon": 88.35, "lat": 22.58},
    "yamuna": {"name": "Yamuna River Basin", "lon": 77.25, "lat": 28.65},
    "new town": {"name": "New Town Rajarhat", "lon": 88.46, "lat": 22.58},
    "rajarhat": {"name": "Rajarhat Action Area", "lon": 88.47, "lat": 22.59},
    "biswa bangla": {"name": "Biswa Bangla Gate", "lon": 88.468, "lat": 22.585},
}


def _parse_polygon_geometry(poly_input: Any) -> Optional[Polygon]:
    """Parse GeoJSON geometry dict, coordinates list, or WKT into Shapely Polygon."""
    if poly_input is None:
        return None
    try:
        if isinstance(poly_input, dict):
            if poly_input.get("type") == "Feature":
                return shape(poly_input["geometry"])
            elif poly_input.get("type") == "Polygon":
                return shape(poly_input)
            elif "coordinates" in poly_input:
                return Polygon(poly_input["coordinates"][0])
        elif isinstance(poly_input, (list, tuple)):
            if len(poly_input) > 0 and isinstance(poly_input[0], (list, tuple)):
                # List of coords [[lon, lat], ...] or [[[lon, lat], ...]]
                if isinstance(poly_input[0][0], (list, tuple)):
                    return Polygon(poly_input[0])
                return Polygon(poly_input)
    except Exception:
        pass
    return None


def _hits_to_results(
    hits,
    session,
    target_loc=None,
    w_semantic_only=False,
    aoi_polygon: Optional[Polygon] = None,
    spatial_relation: Optional[Any] = None,
    max_cloud: Optional[float] = None,
):
    results = []
    tile_ids = [h.payload.get("tile_id") for h in hits if h.payload]
    tile_ids = [t for t in tile_ids if t]
    if not tile_ids:
        return results
    tile_id_objs = []
    for tid in tile_ids:
        tile_id_objs.append(tid)
        try:
            tile_id_objs.append(uuid.UUID(str(tid)))
        except Exception:
            pass

    tiles = {str(t.tile_id): t for t in session.execute(
        select(Tile).options(defer(Tile.geometry)).where(Tile.tile_id.in_(tile_id_objs))
    ).scalars()}

    feedback_rows = session.execute(
        select(Feedback).where(Feedback.target_id.in_(tile_id_objs))
    ).scalars().all()
    confirms = Counter(str(row.target_id) for row in feedback_rows if row.verdict == "confirm")
    rejects = Counter(str(row.target_id) for row in feedback_rows if row.verdict == "reject")

    for h in hits:
        tile_id_str = str((h.payload or {}).get("tile_id"))
        tile = tiles.get(tile_id_str)
        if tile is None:
            continue

        # 1. Precise Geometric Polygon Filtering (Tier 1.1)
        if aoi_polygon is not None:
            tile_pt = Point(tile.lon, tile.lat)
            if not aoi_polygon.contains(tile_pt) and not aoi_polygon.intersects(tile_pt):
                continue

        # 2. Quality / Cloud filtering from NL query
        if max_cloud is not None and tile.cloud_fraction is not None and tile.cloud_fraction > max_cloud:
            continue

        semantic_score = float(h.score)

        # 3. Spatial Proximity / Landmark relevance
        geo_relevance = 1.0
        loc_label = None
        if target_loc:
            dist_sq = (tile.lon - target_loc["lon"]) ** 2 + (tile.lat - target_loc["lat"]) ** 2
            geo_relevance = float(max(0.1, 1.0 - min(dist_sq / 0.5, 0.9)))
            loc_label = target_loc["name"]
        elif spatial_relation is not None:
            # Real geometric proximity (PostGIS / Shapely)
            dist_km = compute_distance_km(tile.lon, tile.lat, spatial_relation.target)
            if dist_km is not None:
                max_d = spatial_relation.distance_km
                if spatial_relation.relation_type == "within" and dist_km > max_d * 1.5:
                    # Filter out or heavily penalize if beyond requested distance
                    continue
                # Proximity boost within range
                geo_relevance = float(max(0.1, 1.0 - min(dist_km / (max_d * 2.0), 0.9)))
                loc_label = f"{spatial_relation.resolved_feature_name or spatial_relation.target} ({dist_km:.1f} km)"

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
            "tile_id": str(tile.tile_id),
            "scene_id": str(tile.scene_id),
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
    aoi_polygon: Optional[Any] = None,
):
    # Tier 1.2 — Natural-Language Filter Parsing
    parsed = parse_natural_language_query(query)
    effective_query = parsed.semantic_query or query

    # Inherit parsed filters if not explicitly provided
    if sensor is None and parsed.sensor:
        sensor = parsed.sensor
    if date_from is None and parsed.date_from:
        date_from = parsed.date_from
    if date_to is None and parsed.date_to:
        date_to = parsed.date_to

    # Tier 1.1 — AOI Polygon Geometry Parsing
    shapely_poly = _parse_polygon_geometry(aoi_polygon)
    if shapely_poly is not None and aoi_bbox is None:
        # Compute polygon envelope for initial fast vector store bbox bounding
        minx, miny, maxx, maxy = shapely_poly.bounds
        aoi_bbox = (minx, miny, maxx, maxy)

    # Detect if user queried a known place / landmark
    q_lower = query.lower()
    target_loc = None
    for kw, loc in KNOWN_GAZETTEER.items():
        if kw in q_lower:
            target_loc = loc
            if aoi_bbox is None and shapely_poly is None:
                delta = 0.35
                aoi_bbox = (
                    loc["lon"] - delta,
                    loc["lat"] - delta,
                    loc["lon"] + delta,
                    loc["lat"] + delta,
                )
            break

    emb = embedding_service.embed_text(effective_query)
    hits = vector_store.search(
        emb.vector, top_k=top_k * 2 if shapely_poly is not None else top_k,
        sensor=sensor, date_from=date_from,
        date_to=date_to, min_similarity=min_similarity, aoi_bbox=aoi_bbox,
    )
    with get_session() as session:
        results = _hits_to_results(
            hits,
            session,
            target_loc=target_loc,
            aoi_polygon=shapely_poly,
            spatial_relation=parsed.spatial_relation,
            max_cloud=parsed.max_cloud_cover,
        )
    return {
        "query": query,
        "effective_semantic_query": effective_query,
        "embedding_model": emb.model_name,
        "embedding_is_placeholder": emb.is_placeholder,
        "parsed_filters": {
            "semantic_query": parsed.semantic_query,
            "spatial_relation": {
                "type": parsed.spatial_relation.relation_type,
                "target": parsed.spatial_relation.target,
                "distance_km": parsed.spatial_relation.distance_km,
                "resolved_name": parsed.spatial_relation.resolved_feature_name,
            } if parsed.spatial_relation else None,
            "date_from": parsed.date_from,
            "date_to": parsed.date_to,
            "max_cloud_cover": parsed.max_cloud_cover,
            "sensor": parsed.sensor,
            "explanation": parsed.explanation,
        },
        "results": results[:top_k],
        "target_location": target_loc,
        "has_polygon_filter": shapely_poly is not None,
    }


def image_to_image_search(
    image: Image.Image,
    top_k: int = 20,
    sensor: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_similarity: float = 0.0,
    aoi_bbox: Optional[tuple] = None,
    aoi_polygon: Optional[Any] = None,
):
    shapely_poly = _parse_polygon_geometry(aoi_polygon)
    if shapely_poly is not None and aoi_bbox is None:
        minx, miny, maxx, maxy = shapely_poly.bounds
        aoi_bbox = (minx, miny, maxx, maxy)

    emb = embedding_service.embed_image(image)
    hits = vector_store.search(
        emb.vector, top_k=top_k * 2 if shapely_poly is not None else top_k,
        sensor=sensor, date_from=date_from,
        date_to=date_to, min_similarity=min_similarity, aoi_bbox=aoi_bbox,
    )
    with get_session() as session:
        results = _hits_to_results(hits, session, aoi_polygon=shapely_poly)
    return {
        "embedding_model": emb.model_name,
        "embedding_is_placeholder": emb.is_placeholder,
        "results": results[:top_k],
        "has_polygon_filter": shapely_poly is not None,
    }

