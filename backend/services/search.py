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

import numpy as np
from PIL import Image
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import defer

from config import settings
from db.database import get_session
from collections import Counter
from db.models import Tile, Scene, Feedback, ChangeResult
from services.embeddings import embedding_service
from services.vector_store import vector_store
from services.ranking import compute_final_score, detect_temporal_query_intent
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


def _sensor_modality(sensor: Optional[str]) -> str:
    value = (sensor or "").lower()
    return "sar" if any(token in value for token in ("sar", "radar", "c-sar")) else "optical"


def _date_value(value: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        if end_of_day and len(str(value)) == 10:
            return parsed.replace(hour=23, minute=59, second=59)
        return parsed
    except ValueError:
        return None


def _spectral_delta_evidence(series: list[Tile], keywords: list[str]) -> dict[str, Any]:
    """Compute a bounded change proxy from the earliest/latest same-location pass."""
    first, last = series[0], series[-1]
    modality = _sensor_modality(last.sensor)
    matched = set(keywords)
    build_intent = bool(matched.intersection({"new", "constructed", "construction", "development", "developed", "expanded", "expansion", "built"}))
    clear_intent = bool(matched.intersection({"cleared", "clearance"}))

    if modality == "optical":
        before, after = first.spectral_indices or {}, last.spectral_indices or {}
        d_ndbi = float(after.get("ndbi_mean", 0.0) or 0.0) - float(before.get("ndbi_mean", 0.0) or 0.0)
        d_ndvi = float(after.get("ndvi_mean", 0.0) or 0.0) - float(before.get("ndvi_mean", 0.0) or 0.0)
        d_ndwi = float(after.get("ndwi_mean", 0.0) or 0.0) - float(before.get("ndwi_mean", 0.0) or 0.0)
        if clear_intent:
            score = 0.75 * np.clip(max(0.0, -d_ndvi) / 0.18, 0.0, 1.0) + 0.25 * np.clip(abs(d_ndbi) / 0.15, 0.0, 1.0)
        elif build_intent:
            score = 0.65 * np.clip(max(0.0, d_ndbi) / 0.15, 0.0, 1.0) + 0.35 * np.clip(max(0.0, -d_ndvi) / 0.18, 0.0, 1.0)
        else:
            score = max(np.clip(abs(d_ndbi) / 0.15, 0.0, 1.0), np.clip(abs(d_ndvi) / 0.18, 0.0, 1.0), np.clip(abs(d_ndwi) / 0.18, 0.0, 1.0))
        deltas = {"d_ndbi": round(d_ndbi, 4), "d_ndvi": round(d_ndvi, 4), "d_ndwi": round(d_ndwi, 4)}
        method = "spectral-delta-proxy"
    else:
        before_means = (first.radiometric_stats or {}).get("band_means", [])
        after_means = (last.radiometric_stats or {}).get("band_means", [])
        before_mean = float(np.mean(before_means)) if before_means else 0.0
        after_mean = float(np.mean(after_means)) if after_means else 0.0
        relative_delta = (after_mean - before_mean) / max(abs(before_mean), 1.0)
        score = np.clip(max(0.0, relative_delta) / 0.25, 0.0, 1.0) if build_intent else np.clip(abs(relative_delta) / 0.30, 0.0, 1.0)
        deltas = {"relative_backscatter_delta": round(relative_delta, 4)}
        method = "sar-feature-delta-proxy"

    support = min(1.0, 0.8 + 0.05 * max(0, len(series) - 2))
    return {
        "score": round(float(np.clip(score * support, 0.0, 1.0)), 4),
        "method": method,
        "modality": modality,
        "observation_count": len(series),
        "date_from": first.acquisition_date.date().isoformat(),
        "date_to": last.acquisition_date.date().isoformat(),
        "deltas": deltas,
    }


def _change_evidence_for_tiles(
    session,
    tiles: Dict[str, Tile],
    keywords: list[str],
    date_from: Optional[str],
    date_to: Optional[str],
) -> dict[str, dict[str, Any]]:
    """Bulk-load temporal peers and return per-candidate physical change evidence."""
    if not tiles:
        return {}
    tolerance = 0.006
    spatial_clauses = [
        and_(Tile.lon.between(tile.lon - tolerance, tile.lon + tolerance), Tile.lat.between(tile.lat - tolerance, tile.lat + tolerance))
        for tile in tiles.values()
    ]
    stmt = select(Tile).options(defer(Tile.geometry)).where(or_(*spatial_clauses), Tile.acquisition_date.is_not(None))
    start, end = _date_value(date_from), _date_value(date_to, end_of_day=True)
    if start is not None:
        stmt = stmt.where(Tile.acquisition_date >= start)
    if end is not None:
        stmt = stmt.where(Tile.acquisition_date <= end)
    peers = session.execute(stmt).scalars().all()

    peer_ids = [str(peer.tile_id) for peer in peers]
    cached = session.execute(
        select(ChangeResult).where(or_(ChangeResult.before_tile_id.in_(peer_ids), ChangeResult.after_tile_id.in_(peer_ids)))
    ).scalars().all() if peer_ids else []

    evidence: dict[str, dict[str, Any]] = {}
    for tile_id, tile in tiles.items():
        modality = _sensor_modality(tile.sensor)
        local = [
            peer for peer in peers
            if _sensor_modality(peer.sensor) == modality
            and abs(peer.lon - tile.lon) <= tolerance
            and abs(peer.lat - tile.lat) <= tolerance
        ]
        nearest_by_day: dict[str, Tile] = {}
        for peer in local:
            day = peer.acquisition_date.date().isoformat()
            current = nearest_by_day.get(day)
            if current is None or (peer.lon - tile.lon) ** 2 + (peer.lat - tile.lat) ** 2 < (current.lon - tile.lon) ** 2 + (current.lat - tile.lat) ** 2:
                nearest_by_day[day] = peer
        series = sorted(nearest_by_day.values(), key=lambda item: item.acquisition_date)
        if len(series) < 2:
            evidence[tile_id] = {"score": 0.0, "method": "insufficient-temporal-evidence", "observation_count": len(series), "modality": modality}
            continue

        proxy = _spectral_delta_evidence(series, keywords)
        local_ids = {str(peer.tile_id) for peer in series}
        engine_rows = [row for row in cached if str(row.before_tile_id) in local_ids and str(row.after_tile_id) in local_ids]
        dense_rows = [row for row in engine_rows if row.method == "dense-multitemporal-change-point"]
        rejected = next(
            (row for row in sorted(dense_rows, key=lambda row: row.created_at or datetime.min, reverse=True)
             if row.persistence_status in {"no_change", "transient_only", "insufficient_data"}),
            None,
        )
        confirmed = [row for row in dense_rows if row.persistence_status == "confirmed"]
        # A dense-series verdict is authoritative. Never let an older bi-temporal
        # pair score overrule a persistence rejection for the same location.
        if rejected is not None:
            proxy.update({
                "score": 0.0,
                "method": rejected.method,
                "engine_result_id": str(rejected.change_id),
                "persistence_status": rejected.persistence_status,
            })
        elif confirmed:
            best = max(confirmed, key=lambda row: float(row.change_score or 0.0))
            proxy.update({
                "score": round(float(np.clip(best.change_score or 0.0, 0.0, 1.0)), 4),
                "method": best.method,
                "engine_result_id": str(best.change_id),
                "persistence_status": best.persistence_status,
            })
        elif len(series) < 5 and engine_rows:
            # Sparse windows intentionally use the bi-temporal fallback.
            best = max(engine_rows, key=lambda row: float(row.change_score or 0.0))
            proxy.update({
                "score": round(float(np.clip(best.change_score or 0.0, 0.0, 1.0)), 4),
                "method": best.method,
                "engine_result_id": str(best.change_id),
                "persistence_status": best.persistence_status,
            })
        evidence[tile_id] = proxy
    return evidence


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
    temporal_query: bool = False,
    temporal_keywords: Optional[list[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
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
    change_evidence = _change_evidence_for_tiles(
        session, tiles, temporal_keywords or [], date_from, date_to
    ) if temporal_query else {}

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

        temporal_evidence = change_evidence.get(tile_id_str, {})
        change_score = float(temporal_evidence.get("score", 0.0)) if temporal_query else None
        final_score, breakdown = compute_final_score(
            semantic_score=semantic_score,
            quality_score=tile.quality_score or 0.8,
            geo_relevance=geo_relevance,
            metadata_match=1.0,
            change_confidence=change_score,
            is_placeholder=tile.embedding_is_placeholder,
            temporal_query=temporal_query,
        )
        feedback_adjustment = 0.08 * confirms[tile.tile_id] - 0.08 * rejects[tile.tile_id]
        final_score = float(min(1.0, max(0.0, final_score + feedback_adjustment)))
        breakdown["feedback_adjustment"] = round(feedback_adjustment, 3)
        breakdown["geo"] = round(geo_relevance, 3)
        if temporal_query:
            breakdown["change_evidence"] = temporal_evidence

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
            "change_score": change_score,
            "change_evidence": temporal_evidence if temporal_query else None,
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
    if temporal_query:
        # For temporal change queries, sort candidates primarily by observed physical change evidence (highest change first),
        # using final_score as the secondary tie-breaker.
        results.sort(
            key=lambda r: (
                float(r.get("change_score") or 0.0),
                float(r.get("final_score") or 0.0),
            ),
            reverse=True,
        )
        # Return candidate locations in change-aware ranked order,
        # without discarding valid candidate sites.
        unique_results = []
        seen_locations = set()
        for result in results:
            key = (round(float(result["lon"]), 4), round(float(result["lat"]), 4), _sensor_modality(result.get("sensor")))
            if key in seen_locations:
                continue
            seen_locations.add(key)
            unique_results.append(result)
        results = unique_results
    else:
        results.sort(key=lambda r: float(r.get("final_score") or 0.0), reverse=True)
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
    temporal_query, temporal_keywords = detect_temporal_query_intent(query)

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
    loc_bbox = None
    if target_loc is not None:
        if target_loc.get("bbox"):
            tb = target_loc["bbox"]
            loc_bbox = (tb[0] - 0.04, tb[1] - 0.04, tb[2] + 0.04, tb[3] + 0.04)
        elif target_loc.get("lon") is not None and target_loc.get("lat") is not None:
            t_lon, t_lat = target_loc["lon"], target_loc["lat"]
            loc_bbox = (t_lon - 0.07, t_lat - 0.07, t_lon + 0.07, t_lat + 0.07)

    if aoi_bbox is None:
        effective_bbox = loc_bbox
    elif loc_bbox is not None:
        # Intersect viewport aoi_bbox with target location box if feasible
        inter = (
            max(aoi_bbox[0], loc_bbox[0]),
            max(aoi_bbox[1], loc_bbox[1]),
            min(aoi_bbox[2], loc_bbox[2]),
            min(aoi_bbox[3], loc_bbox[3]),
        )
        if inter[0] < inter[2] and inter[1] < inter[3]:
            effective_bbox = inter
        else:
            effective_bbox = loc_bbox
    else:
        effective_bbox = aoi_bbox

    emb = embedding_service.embed_text(effective_query)
    search_k = top_k * 6 if temporal_query else (top_k * 4 if (shapely_poly is not None or target_loc is not None) else top_k)
    hits = vector_store.search(
        emb.vector, top_k=search_k,
        sensor=sensor, date_from=date_from,
        date_to=date_to, min_similarity=min_similarity, aoi_bbox=effective_bbox,
    )
    if len(hits) < 3 and effective_bbox is not None:
        # Fallback to broader search if candidate window was too tight
        hits = vector_store.search(
            emb.vector, top_k=search_k,
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
            temporal_query=temporal_query,
            temporal_keywords=temporal_keywords,
            date_from=date_from,
            date_to=date_to,
        )
    return {
        "query": query,
        "effective_semantic_query": effective_query,
        "embedding_model": emb.model_name,
        "embedding_is_placeholder": emb.is_placeholder,
        "temporal_query": temporal_query,
        "temporal_keywords": temporal_keywords,
        "ranking_mode": "change-aware" if temporal_query else "hybrid",
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
            "temporal_change_intent": temporal_query,
            "temporal_keywords": temporal_keywords,
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
