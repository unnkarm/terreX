"""
Tier 1.2 — Natural-Language Filter Parsing with GLiNER & Geocoding.

Zero-shot entity extraction powered by GLiNER (Generalist and Lightweight Named Entity Recognition)
for ultra-fast, sub-second natural language query parsing. Operates 100% in-process on CPU
with zero external server/socket dependencies (no Ollama daemon required).

Parses compound free-text queries like:
- "large new structures within 5km of rivers after January 2024, excluding cloudy imagery"
- "new roads near biswa bangla gate before 2025"
- "water extent variation along hooghly river with clear sky on Sentinel-2"
- "flooded agricultural land in Rajarhat Action Area on Sentinel-1 SAR since September 2024"

Extracts structured filters:
- semantic_query (pure visual subject for CLIP vector search)
- spatial_relation: { relation_type: "within"|"near", target: str, distance_km: float, resolved_feature_name: str }
- date_range: { date_from: "YYYY-MM-DD", date_to: "YYYY-MM-DD" }
- quality_filters: { max_cloud_cover: float, min_quality_score: float }
- sensor: "Sentinel-2" | "Sentinel-1" | "Landsat-8" | "LISS-4" | "LISS-3" | "AWiFS"

Includes offline vector geometries for real spatial distance computations (PostGIS ST_DWithin / Shapely).
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import nearest_points

from services.offline_geocoder import offline_geocoder

logger = logging.getLogger("terrex.nlp_filter")

MONTH_MAP = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}


@dataclass
class SpatialConstraint:
    relation_type: str  # "within" | "near"
    target: str
    distance_km: float
    resolved_feature_name: Optional[str] = None


@dataclass
class ParsedQueryFilters:
    raw_query: str
    semantic_query: str
    spatial_relation: Optional[SpatialConstraint] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    max_cloud_cover: Optional[float] = None
    min_quality_score: Optional[float] = None
    sensor: Optional[str] = None
    explanation: List[str] = field(default_factory=list)


def compute_distance_km(lon: float, lat: float, target_name: str) -> Optional[float]:
    """
    Computes approximate geodesic/Euclidean distance in kilometers between
    a (lon, lat) point and a pre-cached offline geometry feature.
    1 degree latitude ~ 111.0 km, 1 degree longitude at 22°N ~ 102.8 km.
    """
    match_geom = None
    res = offline_geocoder.geocode(target_name)
    if res and "geometry" in res:
        from shapely.geometry import shape
        match_geom = shape(res["geometry"])
    elif res and "lon" in res and "lat" in res:
        match_geom = Point(res["lon"], res["lat"])

    if match_geom is None:
        return None

    pt = Point(lon, lat)
    def _to_km(p: Point) -> Tuple[float, float]:
        return (p.x * 102.8, p.y * 111.0)

    if match_geom.geom_type == "Point":
        pt_km = _to_km(pt)
        tgt_km = _to_km(match_geom)
        return float(((pt_km[0] - tgt_km[0]) ** 2 + (pt_km[1] - tgt_km[1]) ** 2) ** 0.5)

    deg_dist = match_geom.distance(pt)
    return float(deg_dist * 107.0)  # Average 107 km per degree


# =========================================================================
# GLiNER In-Process Zero-Shot NER Engine
# =========================================================================

_gliner_model = None

def get_gliner_model():
    """
    Lazy-loads the lightweight GLiNER transformer model.
    Runs locally in-process on CPU (~150MB, sub-second inference).
    """
    global _gliner_model
    if _gliner_model is None:
        import warnings
        import logging as _logging
        _tf_logger = _logging.getLogger("transformers")
        _prev_level = _tf_logger.level
        _tf_logger.setLevel(_logging.ERROR)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                from gliner import GLiNER
                t0 = time.perf_counter()
                _gliner_model = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
                logger.info(f"GLiNER zero-shot NER model initialized in {time.perf_counter()-t0:.2f}s")
            except Exception as e:
                logger.warning(f"Failed to load GLiNER model ({e}). Will use fallback regex/geocoder parser.")
                _gliner_model = False
            finally:
                _tf_logger.setLevel(_prev_level)
    return _gliner_model if _gliner_model is not False else None


def normalize_sensor(sensor_str: str) -> Optional[str]:
    """Normalizes raw satellite sensor entity strings to standardized names."""
    s = sensor_str.lower().strip()
    if "sentinel-2" in s or "sentinel 2" in s or "s2" in s:
        return "Sentinel-2"
    if "sentinel-1" in s or "sentinel 1" in s or "s1" in s or "sar" in s:
        return "Sentinel-1"
    if "landsat-8" in s or "landsat 8" in s or "landsat" in s or "l8" in s:
        return "Landsat-8"
    if "liss-4" in s or "liss 4" in s or "liss4" in s:
        return "LISS-4"
    if "liss-3" in s or "liss 3" in s or "liss3" in s:
        return "LISS-3"
    if "awifs" in s:
        return "AWiFS"
    return sensor_str.strip()


def parse_with_gliner(query: str) -> Optional[ParsedQueryFilters]:
    """
    Fast zero-shot entity extraction via GLiNER + TerreX offline geocoding.
    Extracts locations, sensors, dates, cloud cover limits, and isolates
    the pure visual concept for CLIP embedding search.
    """
    model = get_gliner_model()
    if not model:
        return None

    cleaned = query.strip(" '\"\t\r\n")
    explanation: List[str] = []

    labels = [
        "geographic location or landmark",
        "satellite sensor",
        "date range",
        "cloud cover threshold",
        "distance measurement"
    ]

    try:
        entities = model.predict_entities(cleaned, labels, threshold=0.32)
    except Exception as e:
        logger.warning(f"GLiNER prediction error: {e}")
        return None

    # 1. Location & Spatial Relation
    spatial_relation = None
    loc_entities = [e for e in entities if e["label"] == "geographic location or landmark"]
    
    # Filter and prioritize entities that resolve in offline geocoder
    best_loc = None
    best_geo = None
    for loc_e in loc_entities:
        geo = offline_geocoder.geocode(loc_e["text"])
        if geo:
            best_loc = loc_e["text"]
            best_geo = geo
            break

    if not best_loc and loc_entities:
        best_loc = loc_entities[0]["text"]
        best_geo = offline_geocoder.geocode(best_loc)

    GENERIC_LANDCOVER = {"river", "rivers", "water", "lake", "lakes", "road", "roads", "forest", "forests", "building", "buildings", "field", "fields", "land", "trees", "ocean", "sea"}

    has_spatial_prep = bool(re.search(r"\b(?:within|inside|at\s+most|near|close to|along|beside|adjacent to|around|in|of|at)\b", cleaned, re.IGNORECASE))
    
    # If the detected location is a generic land cover word without explicit spatial context, skip it as a location filter
    if best_loc and best_loc.lower().strip() in GENERIC_LANDCOVER and not has_spatial_prep:
        best_loc = None
        best_geo = None

    if best_loc:
        res_name = best_geo["name"] if best_geo else best_loc.title()

        # Proximity distance and relation type
        dist_val = 3.0
        rel_type = "near"

        dist_match = re.search(
            r"\b(?:within|inside|at\s+most)\s+(\d+(?:\.\d+)?)\s*(?:km|kilometers|m|meters)?\b",
            cleaned,
            re.IGNORECASE
        )
        if dist_match:
            dist_val = float(dist_match.group(1))
            rel_type = "within"
        elif re.search(r"\b(?:near|close to|along|beside|adjacent to|around|in)\b", cleaned, re.IGNORECASE):
            rel_type = "near"

        spatial_relation = SpatialConstraint(
            relation_type=rel_type,
            target=best_loc,
            distance_km=dist_val,
            resolved_feature_name=res_name,
        )
        explanation.append(f"GLiNER location: {best_loc} (Resolved: {res_name}, Proximity: {rel_type} {dist_val}km)")

    # 2. Satellite Sensor
    sensor = None
    sensor_entities = [e for e in entities if e["label"] == "satellite sensor"]
    if sensor_entities:
        sensor = normalize_sensor(sensor_entities[0]["text"])
        explanation.append(f"GLiNER sensor: {sensor}")
    else:
        if re.search(r"\b(sentinel[\s-]?2|s2)\b", cleaned, re.IGNORECASE):
            sensor = "Sentinel-2"
            explanation.append("Extracted sensor: Sentinel-2")
        elif re.search(r"\b(sentinel[\s-]?1|s1|sar)\b", cleaned, re.IGNORECASE):
            sensor = "Sentinel-1"
            explanation.append("Extracted sensor: Sentinel-1")
        elif re.search(r"\b(landsat[\s-]?8|landsat|l8)\b", cleaned, re.IGNORECASE):
            sensor = "Landsat-8"
            explanation.append("Extracted sensor: Landsat-8")
        elif re.search(r"\b(liss[\s-]?4)\b", cleaned, re.IGNORECASE):
            sensor = "LISS-4"
            explanation.append("Extracted sensor: LISS-4")
        elif re.search(r"\b(liss[\s-]?3)\b", cleaned, re.IGNORECASE):
            sensor = "LISS-3"
            explanation.append("Extracted sensor: LISS-3")
        elif re.search(r"\b(awifs)\b", cleaned, re.IGNORECASE):
            sensor = "AWiFS"
            explanation.append("Extracted sensor: AWiFS")

    # 3. Cloud Cover Constraint
    max_cloud = None
    cloud_pattern = r"(?:(?:max(?:imum)?\s+)?cloud(?:y| cover)?|cloud(?:y| cover)?\s*(?:<|less than|under|below|max|maximum|<=|:))\s*(\d+)%?"
    cloud_match = re.search(cloud_pattern, cleaned, re.IGNORECASE)
    if cloud_match:
        max_cloud = float(cloud_match.group(1)) / 100.0
        explanation.append(f"Filtered maximum cloud cover to {int(max_cloud * 100)}%")
    elif re.search(r"(?:excluding|without|no)\s+cloudy(?:\s+imagery)?", cleaned, re.IGNORECASE):
        max_cloud = 0.15
        explanation.append("Excluded cloudy imagery (max cloud < 15%)")
    elif re.search(r"clear\s+sky(?:\s+only)?", cleaned, re.IGNORECASE):
        max_cloud = 0.10
        explanation.append("Enforced clear sky filter (max cloud < 10%)")

    # 4. Date Ranges (Absolute and Relative)
    date_from = None
    date_to = None

    rel_match = re.search(
        r"\b(?:in\s+)?(?:the\s+)?(?:last|past)\s+(\d+)?\s*(years?|yrs?|months?|mos?)\b",
        cleaned,
        re.IGNORECASE,
    )
    if rel_match:
        val_str, unit = rel_match.group(1), rel_match.group(2).lower()
        val = int(val_str) if val_str else 1
        now_year = datetime.now().year
        if "year" in unit or "yr" in unit:
            date_from = f"{now_year - val}-01-01"
        else:
            # Months
            now_month = datetime.now().month
            tot_months = now_year * 12 + now_month - val
            target_year = tot_months // 12
            target_month = max(1, tot_months % 12)
            date_from = f"{target_year:04d}-{target_month:02d}-01"
        explanation.append(f"Applied relative date lower-bound: >= {date_from}")

    after_match = re.search(
        r"\b(?:after|since|from|post)\s+([a-zA-Z]+)?\s*(\d{4})(?:-(\d{2})-(\d{2}))?\b",
        cleaned,
        re.IGNORECASE,
    )
    if after_match and not date_from:
        month_str, year_str, m_num, d_num = after_match.group(1), after_match.group(2), after_match.group(3), after_match.group(4)
        if m_num and d_num:
            date_from = f"{year_str}-{m_num}-{d_num}"
        elif month_str and month_str.lower() in MONTH_MAP:
            date_from = f"{year_str}-{MONTH_MAP[month_str.lower()]}-01"
        else:
            date_from = f"{year_str}-01-01"
        explanation.append(f"Applied date lower-bound: >= {date_from}")

    before_match = re.search(
        r"\b(?:before|until|to|prior to)\s+([a-zA-Z]+)?\s*(\d{4})(?:-(\d{2})-(\d{2}))?\b",
        cleaned,
        re.IGNORECASE,
    )
    if before_match:
        month_str, year_str, m_num, d_num = before_match.group(1), before_match.group(2), before_match.group(3), before_match.group(4)
        if m_num and d_num:
            date_to = f"{year_str}-{m_num}-{d_num}"
        elif month_str and month_str.lower() in MONTH_MAP:
            date_to = f"{year_str}-{MONTH_MAP[month_str.lower()]}-28"
        else:
            date_to = f"{year_str}-12-31"
        explanation.append(f"Applied date upper-bound: <= {date_to}")

    # 5. Extract Core Semantic Query (clean out spatial, sensor, temporal, cloud terms)
    sem_text = cleaned
    if rel_match:
        sem_text = sem_text.replace(rel_match.group(0), " ")
    if after_match:
        sem_text = sem_text.replace(after_match.group(0), " ")
    if before_match:
        sem_text = sem_text.replace(before_match.group(0), " ")
    if cloud_match:
        sem_text = sem_text.replace(cloud_match.group(0), " ")
    sem_text = re.sub(r"(?:excluding|without|no)\s+cloudy(?:\s+imagery)?", " ", sem_text, flags=re.IGNORECASE)
    sem_text = re.sub(r"clear\s+sky(?:\s+only)?", " ", sem_text, flags=re.IGNORECASE)

    # Remove confirmed location entities
    if best_loc:
        sem_text = re.sub(re.escape(best_loc), " ", sem_text, flags=re.IGNORECASE)
    for loc_e in loc_entities:
        if offline_geocoder.geocode(loc_e["text"]):
            sem_text = re.sub(re.escape(loc_e["text"]), " ", sem_text, flags=re.IGNORECASE)

    # Remove sensor entities
    for s_e in sensor_entities:
        sem_text = re.sub(re.escape(s_e["text"]), " ", sem_text, flags=re.IGNORECASE)
    sem_text = re.sub(r"\b(sentinel[\s-]?[12]|sar|landsat[\s-]?8|liss[\s-]?[34]|awifs)\b", " ", sem_text, flags=re.IGNORECASE)

    # Remove distance measurements
    sem_text = re.sub(r"\b(?:within|inside|at\s+most)\s+(\d+(?:\.\d+)?)\s*(?:km|kilometers|m|meters)?(?:\s+of)?\b", " ", sem_text, flags=re.IGNORECASE)
    sem_text = re.sub(r"\b\d+(\.\d+)?\s*(km|kilometers|m|meters)\b", " ", sem_text, flags=re.IGNORECASE)

    # Clean dangling spatial prepositions & punctuation
    sem_text = re.sub(r"\b(?:near|close to|along|beside|adjacent to|around|in|of|on|from|with|at|under|over)\b", " ", sem_text, flags=re.IGNORECASE)
    sem_text = re.sub(r"[,\.;:\-_]+", " ", sem_text)
    sem_text = re.sub(r"\s+", " ", sem_text).strip()

    if not sem_text:
        sem_text = query.strip()

    return ParsedQueryFilters(
        raw_query=query,
        semantic_query=sem_text,
        spatial_relation=spatial_relation,
        date_from=date_from,
        date_to=date_to,
        max_cloud_cover=max_cloud,
        sensor=sensor,
        explanation=explanation,
    )


# =========================================================================
# Fallback Regex / Rule-Based Parser
# =========================================================================

def _parse_regex_fallback(query: str) -> ParsedQueryFilters:
    """
    Deterministic rule-based fallback parser when ML model is inactive.
    """
    cleaned = query.strip()
    explanation: List[str] = []

    # 1. Quality / Cloud Filters
    max_cloud = None
    cloud_match = re.search(r"cloud(?:y| cover)?\s*(?:<|less than|under|below|max)\s*(\d+)%?", cleaned, re.IGNORECASE)
    if cloud_match:
        max_cloud = float(cloud_match.group(1)) / 100.0
        cleaned = re.sub(cloud_match.group(0), "", cleaned, flags=re.IGNORECASE)
        explanation.append(f"Filtered maximum cloud cover to {int(max_cloud * 100)}%")
    elif re.search(r"(?:excluding|without|no)\s+cloudy(?:\s+imagery)?", cleaned, re.IGNORECASE):
        max_cloud = 0.15
        cleaned = re.sub(r"(?:excluding|without|no)\s+cloudy(?:\s+imagery)?", "", cleaned, flags=re.IGNORECASE)
        explanation.append("Excluded cloudy imagery (max cloud < 15%)")
    elif re.search(r"clear\s+sky(?:\s+only)?", cleaned, re.IGNORECASE):
        max_cloud = 0.10
        cleaned = re.sub(r"clear\s+sky(?:\s+only)?", "", cleaned, flags=re.IGNORECASE)
        explanation.append("Enforced clear sky filter (max cloud < 10%)")

    # 2. Sensor
    sensor = None
    if re.search(r"\b(sentinel[\s-]?2|s2)\b", cleaned, re.IGNORECASE):
        sensor = "Sentinel-2"
        cleaned = re.sub(r"\b(from\s+|on\s+)?(sentinel[\s-]?2|s2)\b", "", cleaned, flags=re.IGNORECASE)
        explanation.append("Restricted to Sentinel-2 sensor")
    elif re.search(r"\b(sentinel[\s-]?1|s1|sar)\b", cleaned, re.IGNORECASE):
        sensor = "Sentinel-1"
        cleaned = re.sub(r"\b(from\s+|on\s+)?(sentinel[\s-]?1|s1|sar)\b", "", cleaned, flags=re.IGNORECASE)
        explanation.append("Restricted to Sentinel-1 sensor")
    elif re.search(r"\b(landsat[\s-]?8|landsat|l8)\b", cleaned, re.IGNORECASE):
        sensor = "Landsat-8"
        cleaned = re.sub(r"\b(from\s+|on\s+)?(landsat[\s-]?8|landsat|l8)\b", "", cleaned, flags=re.IGNORECASE)
        explanation.append("Restricted to Landsat-8 sensor")

    # 3. Date Ranges
    date_from = None
    date_to = None

    after_match = re.search(
        r"\b(?:after|since|from|post)\s+([a-zA-Z]+)?\s*(\d{4})(?:-(\d{2})-(\d{2}))?\b",
        cleaned,
        re.IGNORECASE,
    )
    if after_match:
        month_str = after_match.group(1)
        year_str = after_match.group(2)
        m_num = after_match.group(3)
        d_num = after_match.group(4)

        if m_num and d_num:
            date_from = f"{year_str}-{m_num}-{d_num}"
        elif month_str and month_str.lower() in MONTH_MAP:
            date_from = f"{year_str}-{MONTH_MAP[month_str.lower()]}-01"
        else:
            date_from = f"{year_str}-01-01"

        cleaned = re.sub(after_match.group(0), "", cleaned, flags=re.IGNORECASE)
        explanation.append(f"Applied date lower-bound: >= {date_from}")

    before_match = re.search(
        r"\b(?:before|until|to|prior to)\s+([a-zA-Z]+)?\s*(\d{4})(?:-(\d{2})-(\d{2}))?\b",
        cleaned,
        re.IGNORECASE,
    )
    if before_match:
        month_str = before_match.group(1)
        year_str = before_match.group(2)
        m_num = before_match.group(3)
        d_num = before_match.group(4)

        if m_num and d_num:
            date_to = f"{year_str}-{m_num}-{d_num}"
        elif month_str and month_str.lower() in MONTH_MAP:
            date_to = f"{year_str}-{MONTH_MAP[month_str.lower()]}-28"
        else:
            date_to = f"{year_str}-12-31"

        cleaned = re.sub(before_match.group(0), "", cleaned, flags=re.IGNORECASE)
        explanation.append(f"Applied date upper-bound: <= {date_to}")

    # 4. Spatial Relations
    spatial_relation = None
    dist_match = re.search(
        r"\b(?:within|inside|at\s+most)\s+(\d+(?:\.\d+)?)\s*(?:km|kilometers|m|meters)?\s*(?:of|from|around)\s+([a-zA-Z\s]+?)(?:,|\.|$|\bafter\b|\bbefore\b|\bexcluding\b)",
        cleaned,
        re.IGNORECASE,
    )
    if dist_match:
        dist_val = float(dist_match.group(1))
        target_raw = dist_match.group(2).strip().lower()
        target = target_raw.rstrip("s")
        geo_res = offline_geocoder.geocode(target)
        res_name = geo_res["name"] if geo_res else target.title()
        spatial_relation = SpatialConstraint(
            relation_type="within",
            target=target,
            distance_km=dist_val,
            resolved_feature_name=res_name,
        )
        cleaned = re.sub(dist_match.group(0), "", cleaned, flags=re.IGNORECASE)
        explanation.append(f"Enforced spatial proximity: within {dist_val}km of {target}")
    else:
        near_match = re.search(
            r"\b(?:near|close to|along|beside|adjacent to)\s+([a-zA-Z\s]+?)(?:,|\.|$|\bafter\b|\bbefore\b|\bexcluding\b)",
            cleaned,
            re.IGNORECASE,
        )
        if near_match:
            target_raw = near_match.group(1).strip().lower()
            target = target_raw.rstrip("s")
            geo_res = offline_geocoder.geocode(target)
            res_name = geo_res["name"] if geo_res else target.title()
            spatial_relation = SpatialConstraint(
                relation_type="near",
                target=target,
                distance_km=3.0,
                resolved_feature_name=res_name,
            )
            cleaned = re.sub(near_match.group(0), "", cleaned, flags=re.IGNORECASE)
            explanation.append(f"Enforced spatial proximity: near {target} (~3km)")

    semantic_query = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
    if not semantic_query:
        semantic_query = query.strip()

    return ParsedQueryFilters(
        raw_query=query,
        semantic_query=semantic_query,
        spatial_relation=spatial_relation,
        date_from=date_from,
        date_to=date_to,
        max_cloud_cover=max_cloud,
        sensor=sensor,
        explanation=explanation,
    )


# =========================================================================
# Public API Entrypoint
# =========================================================================

def parse_natural_language_query(query: str) -> ParsedQueryFilters:
    """
    Extracts structured constraints from natural language queries.
    Uses in-process GLiNER zero-shot transformer model first (~15-50ms),
    with automatic fallback to regex/geocoder parser.
    """
    # 1. Try GLiNER (Fast, in-process, sub-second ML parsing)
    gliner_res = parse_with_gliner(query)
    if gliner_res is not None:
        return gliner_res

    # 2. Deterministic Fallback
    logger.info("Using regex fallback parser for natural language query.")
    return _parse_regex_fallback(query)
