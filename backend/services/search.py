"""
Feature 2 — Semantic (text) search
Feature 3 — Image-to-image search

Both funnel through the same path: embed query -> Qdrant ANN search ->
PostGIS metadata join/filter -> hybrid ranking.
"""
from __future__ import annotations

import math
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
    "salt lake": {"name": "Salt Lake (Bidhannagar)", "lon": 88.41, "lat": 22.58},
    "sector 5": {"name": "Salt Lake Sector V", "lon": 88.433, "lat": 22.574},
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


def _derive_classification_label(
    tile: Tile,
    query: Optional[str] = None,
    place_info: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Dynamically produce an accurate descriptive physical classification label for the candidate tile
    based on the tile's physical spectral indices (NDVI/NDWI/NDBI), radiometric stats,
    sensor modality, and surrounding geographic landmark context.
    """
    spec = tile.spectral_indices or {}
    radio = tile.radiometric_stats or {}
    band_means = radio.get("band_means", [])

    ndvi = float(spec.get("ndvi_mean", 0.0) or 0.0)
    ndwi = float(spec.get("ndwi_mean", 0.0) or 0.0)
    ndbi = float(spec.get("ndbi_mean", 0.0) or 0.0)
    sensor = (tile.sensor or "").upper()

    ftype = place_info.get("feature_type", "") if place_info else ""
    zone = place_info.get("zone", "") if place_info else ""

    # 1. SAR Modality Classification
    if "SAR" in sensor:
        if ndbi > -0.486:
            return "RADAR HIGH-SCATTER URBAN STRUCTURE"
        elif ndbi < -0.490:
            return "RADAR SMOOTH SURFACE / WATERWAY"
        else:
            return "RADAR MIXED TERRAIN & BUILT-UP"

    # 2. Optical Multi-Spectral (MSI) Classification
    # Check for Water Body (River, Canal, Wetland, Jheel)
    if ndwi > 0.05 or (ndwi > -0.15 and ndvi < -0.05 and ndbi < -0.15):
        if "wetland" in ftype or "wetland" in zone.lower():
            return "WETLAND & AQUACULTURE BASIN"
        return "HOOGHLY WATERWAY & AQUATIC BASIN"

    if ndwi > -0.10 and ndvi > 0.05 and ndbi < -0.10:
        return "WETLAND & RIPARIAN SHORELINE"

    # Check for Dense Vegetation / Forest / Tree Canopy
    if ndvi > 0.30:
        return "DENSE VEGETATED CANOPY / WOODLAND"
    elif ndvi > 0.15:
        if "park" in ftype or "lake" in ftype:
            return "URBAN PARKLAND & CIVIC GREEN"
        return "VEGETATED CANOPY & MIXED GREENS"
    elif ndvi > 0.05 and ndbi < -0.10:
        return "AGRICULTURAL CULTIVATION / AGRO-TERRAIN"

    # Check for High-Density Built-up / Commercial / Industrial
    if ndbi > 0.04 or (len(band_means) >= 3 and sum(band_means) / 3.0 > 130 and ndvi < 0.0):
        if "transit" in ftype or "railway" in ftype:
            return "TRANSIT INFRASTRUCTURE & TERMINAL"
        elif "port" in ftype or "maritime" in ftype:
            return "PORT & MARITIME LOGISTICS"
        elif "commercial" in ftype or "it" in ftype:
            return "HIGH-DENSITY COMMERCIAL FABRIC"
        elif "airport" in ftype:
            return "AIRPORT & RUNWAY INFRASTRUCTURE"
        return "HIGH-DENSITY URBAN BUILT-UP"

    if ndbi > -0.08 or (len(band_means) >= 3 and sum(band_means) / 3.0 > 85):
        if "residential" in ftype:
            return "PLANNED RESIDENTIAL URBAN FABRIC"
        return "URBAN RESIDENTIAL DEVELOPMENT"

    # Low reflection / open terrain / cleared ground
    if ndbi < -0.20 and ndvi < 0.05:
        return "OPEN TERRAIN & LOW-REFLECTIVE GROUND"

    return "MIXED URBAN & PERI-URBAN TERRAIN"


def _hits_to_results(
    hits,
    session,
    target_loc=None,
    w_semantic_only=False,
    aoi_polygon: Optional[Polygon] = None,
    spatial_relation: Optional[Any] = None,
    max_cloud: Optional[float] = None,
    query: Optional[str] = None,
):
    from services.offline_geocoder import offline_geocoder

    results = []
    tile_ids = [str(h.payload.get("tile_id")) for h in hits if h.payload and h.payload.get("tile_id")]
    tile_ids = list(dict.fromkeys(tile_ids))
    if not tile_ids:
        return results

    tiles = {str(t.tile_id): t for t in session.execute(
        select(Tile).options(defer(Tile.geometry)).where(Tile.tile_id.in_(tile_ids))
    ).scalars()}
    scene_ids = list({str(t.scene_id) for t in tiles.values()})
    scenes = {str(s.scene_id): s for s in session.execute(
        select(Scene).where(Scene.scene_id.in_(scene_ids))
    ).scalars()}

    feedback_rows = session.execute(
        select(Feedback).where(Feedback.target_id.in_(tile_ids))
    ).scalars().all()
    confirms = Counter(str(row.target_id) for row in feedback_rows if row.verdict == "confirm")
    rejects = Counter(str(row.target_id) for row in feedback_rows if row.verdict == "reject")

    for h in hits:
        tile_id_str = str((h.payload or {}).get("tile_id"))
        tile = tiles.get(tile_id_str)
        if tile is None:
            continue
        scene = scenes.get(str(tile.scene_id))

        # 1. Precise Geometric Polygon Filtering (Tier 1.1)
        if aoi_polygon is not None:
            tile_pt = Point(tile.lon, tile.lat)
            if not aoi_polygon.contains(tile_pt) and not aoi_polygon.intersects(tile_pt):
                continue

        # 2. Quality / Cloud filtering from NL query
        if max_cloud is not None and tile.cloud_fraction is not None and tile.cloud_fraction > max_cloud:
            continue

        semantic_score = float(h.score)

        # 3. Dynamic reverse-geocoding for this specific tile's coordinates
        tile_place = offline_geocoder.reverse_geocode(tile.lon, tile.lat)
        loc_label = tile_place["subtitle"]

        # 4. Spatial Proximity / Landmark relevance
        geo_relevance = 1.0
        if target_loc:
            tgt_lon = target_loc.get("lon")
            tgt_lat = target_loc.get("lat")
            if tgt_lon is not None and tgt_lat is not None:
                d_lon_km = (tile.lon - tgt_lon) * 102.8
                d_lat_km = (tile.lat - tgt_lat) * 111.0
                dist_km = math.sqrt(d_lon_km ** 2 + d_lat_km ** 2)

                # If query specifically targeted this location, exclude completely out-of-district tiles
                if dist_km > 12.0:
                    continue
                elif dist_km <= 2.0:
                    geo_relevance = 1.0
                else:
                    geo_relevance = float(math.exp(-0.5 * ((dist_km - 2.0) / 2.5) ** 2))
        elif spatial_relation is not None:
            dist_km = compute_distance_km(tile.lon, tile.lat, spatial_relation.target)
            if dist_km is not None:
                max_d = spatial_relation.distance_km
                if spatial_relation.relation_type in ("within", "in") and dist_km > max_d * 2.0:
                    continue
                elif dist_km > 12.0:
                    continue
                geo_relevance = float(math.exp(-0.5 * (max(0.0, dist_km - max_d) / 2.5) ** 2))

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

        class_label = _derive_classification_label(tile, query=query, place_info=tile_place)

        results.append({
            "tile_id": str(tile.tile_id),
            "scene_id": str(tile.scene_id),
            "lon": tile.lon,
            "lat": tile.lat,
            "classification_label": class_label,
            "similarity_score": breakdown.get("semantic", semantic_score),
            "raw_similarity": semantic_score,
            "final_score": final_score,
            "score_breakdown": breakdown,
            "acquisition_date": tile.acquisition_date.isoformat() if tile.acquisition_date else None,
            "sensor": tile.sensor,
            "quality_score": tile.quality_score,
            "cloud_fraction": tile.cloud_fraction,
            "cloud_cover_pct": scene.cloud_cover_pct if scene else None,
            "thumbnail_path": tile.thumbnail_path,
            "embedding_model": tile.embedding_model,
            "embedding_is_placeholder": tile.embedding_is_placeholder,
            "location_name": loc_label,
            "neighborhood": tile_place.get("name"),
            "zone": tile_place.get("zone"),
            "source_portal": scene.source_portal if scene else None,
            "underlying_dataset": scene.underlying_dataset if scene else None,
            "license": scene.license_source if scene else None,
            "provenance": scene.provenance if scene else None,
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
        minx, miny, maxx, maxy = shapely_poly.bounds
        aoi_bbox = (minx, miny, maxx, maxy)

    from services.offline_geocoder import offline_geocoder
    target_loc = None

    # Check if a location name was extracted by the NLP/LLM filter
    if parsed.spatial_relation and parsed.spatial_relation.target:
        geo_res = offline_geocoder.geocode(parsed.spatial_relation.target)
        if geo_res:
            target_loc = geo_res

    # If not found via filter extraction, try querying the raw text
    if not target_loc:
        geo_res = offline_geocoder.geocode(query)
        if geo_res:
            target_loc = geo_res

    # Automatically center initial candidate bounding box on extracted location
    effective_bbox = aoi_bbox
    if effective_bbox is None and target_loc is not None:
        if target_loc.get("bbox"):
            tb = target_loc["bbox"]
            effective_bbox = (tb[0] - 0.04, tb[1] - 0.04, tb[2] + 0.04, tb[3] + 0.04)
        elif target_loc.get("lon") is not None and target_loc.get("lat") is not None:
            t_lon, t_lat = target_loc["lon"], target_loc["lat"]
            effective_bbox = (t_lon - 0.07, t_lat - 0.07, t_lon + 0.07, t_lat + 0.07)

    emb = embedding_service.embed_text(effective_query)
    search_k = top_k * 4 if (shapely_poly is not None or target_loc is not None) else top_k
    hits = vector_store.search(
        emb.vector, top_k=search_k,
        sensor=sensor, date_from=date_from,
        date_to=date_to, min_similarity=min_similarity, aoi_bbox=effective_bbox,
    )
    if len(hits) < 3 and effective_bbox is not None and aoi_bbox is None:
        # Fallback to broader search if candidate window was too tight
        hits = vector_store.search(
            emb.vector, top_k=top_k * 4,
            sensor=sensor, date_from=date_from,
            date_to=date_to, min_similarity=min_similarity, aoi_bbox=None,
        )

    with get_session() as session:
        results = _hits_to_results(
            hits,
            session,
            target_loc=target_loc,
            aoi_polygon=shapely_poly,
            spatial_relation=parsed.spatial_relation,
            max_cloud=parsed.max_cloud_cover,
            query=effective_query,
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
