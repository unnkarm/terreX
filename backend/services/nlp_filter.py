"""
Tier 1.2 — Natural-Language Filter Parsing.

Parses compound free-text queries like:
- "large new structures within 5km of rivers after January 2024, excluding cloudy imagery"
- "new roads near biswa bangla gate before 2025"
- "water extent variation along hooghly river with clear sky"

Extracts structured filters:
- semantic_query (core subject)
- spatial_relation: { type: "within"|"near", target: "river"|"road"|"water"|..., distance_km: float }
- date_range: { date_from: "YYYY-MM-DD", date_to: "YYYY-MM-DD" }
- quality_filters: { max_cloud: float, min_quality: float }
- sensor: "Sentinel-2" | "Landsat-8" | etc.

Includes offline vector geometries for real spatial distance computations (PostGIS ST_DWithin / Shapely).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import nearest_points

# Offline staged geographic feature vectors (Hydrology, Roads, Landmarks)
# Coordinates in [lon, lat] (EPSG:4326)
OFFLINE_GEOMETRIES: Dict[str, Dict[str, Any]] = {
    "river": {
        "name": "Hooghly River / Ganga Corridor",
        "type": "LineString",
        "geometry": LineString([
            [88.30, 22.80], [88.32, 22.70], [88.34, 22.62], [88.35, 22.58],
            [88.34, 22.52], [88.32, 22.45], [88.28, 22.35], [88.20, 22.20],
        ]),
    },
    "hooghly": {
        "name": "Hooghly River Basin",
        "type": "LineString",
        "geometry": LineString([
            [88.30, 22.80], [88.32, 22.70], [88.34, 22.62], [88.35, 22.58],
            [88.34, 22.52], [88.32, 22.45], [88.28, 22.35],
        ]),
    },
    "yamuna": {
        "name": "Yamuna River Corridor (Delhi)",
        "type": "LineString",
        "geometry": LineString([
            [77.21, 28.75], [77.23, 28.70], [77.25, 28.65], [77.27, 28.60],
            [77.30, 28.52], [77.33, 28.45],
        ]),
    },
    "water": {
        "name": "Water Bodies / Wetlands Corridor",
        "type": "LineString",
        "geometry": LineString([
            [88.42, 22.55], [88.45, 22.54], [88.48, 22.52], [88.50, 22.50],
        ]),
    },
    "lake": {
        "name": "East Kolkata Wetlands & Lakes",
        "type": "Polygon",
        "geometry": Polygon([
            [88.42, 22.50], [88.48, 22.50], [88.48, 22.56], [88.42, 22.56], [88.42, 22.50],
        ]),
    },
    "road": {
        "name": "Major Arterial Highway Corridor",
        "type": "LineString",
        "geometry": LineString([
            [88.25, 22.58], [88.30, 22.58], [88.40, 22.58], [88.47, 22.58], [88.52, 22.58],
        ]),
    },
    "highway": {
        "name": "Expressway Corridor",
        "type": "LineString",
        "geometry": LineString([
            [88.40, 22.65], [88.44, 22.60], [88.47, 22.58], [88.48, 22.52],
        ]),
    },
    "biswa bangla": {
        "name": "Biswa Bangla Gate Corridor",
        "type": "Point",
        "geometry": Point(88.468, 22.585),
    },
    "new town": {
        "name": "New Town Rajarhat Corridor",
        "type": "Point",
        "geometry": Point(88.460, 22.580),
    },
}

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
    key = target_name.lower().strip()
    match_geom = None
    for k, v in OFFLINE_GEOMETRIES.items():
        if k in key or key in k:
            match_geom = v["geometry"]
            break

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


def parse_natural_language_query(query: str) -> ParsedQueryFilters:
    """
    Extracts structured constraints from natural language queries.
    Handles compound queries without requiring external cloud LLM.
    """
    cleaned = query.strip()
    explanation: List[str] = []

    # 1. Extract Quality / Cloud Filters
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

    # 2. Extract Sensor
    sensor = None
    if re.search(r"\b(sentinel[\s-]?2|s2)\b", cleaned, re.IGNORECASE):
        sensor = "Sentinel-2"
        cleaned = re.sub(r"\b(from\s+|on\s+)?(sentinel[\s-]?2|s2)\b", "", cleaned, flags=re.IGNORECASE)
        explanation.append("Restricted to Sentinel-2 sensor")
    elif re.search(r"\b(landsat[\s-]?8|landsat|l8)\b", cleaned, re.IGNORECASE):
        sensor = "Landsat-8"
        cleaned = re.sub(r"\b(from\s+|on\s+)?(landsat[\s-]?8|landsat|l8)\b", "", cleaned, flags=re.IGNORECASE)
        explanation.append("Restricted to Landsat-8 sensor")

    # 3. Extract Date Ranges
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

    # 4. Extract Spatial Relations
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
        spatial_relation = SpatialConstraint(
            relation_type="within",
            target=target,
            distance_km=dist_val,
            resolved_feature_name=OFFLINE_GEOMETRIES.get(target, {}).get("name", target.title()),
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
            spatial_relation = SpatialConstraint(
                relation_type="near",
                target=target,
                distance_km=3.0,
                resolved_feature_name=OFFLINE_GEOMETRIES.get(target, {}).get("name", target.title()),
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
