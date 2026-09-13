from __future__ import annotations
import re
import time
import sys
import os
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from shapely.geometry import Point
from gliner import GLiNER

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from services.offline_geocoder import offline_geocoder

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

_gliner_model = None

def get_gliner_model():
    global _gliner_model
    if _gliner_model is None:
        try:
            _gliner_model = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
        except Exception as e:
            print(f"Failed to load GLiNER: {e}")
            _gliner_model = False
    return _gliner_model if _gliner_model is not False else None

def normalize_sensor(sensor_str: str) -> Optional[str]:
    s = sensor_str.lower()
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
    model = get_gliner_model()
    if not model:
        return None

    cleaned = query.strip()
    explanation: List[str] = []
    
    labels = [
        "geographic location or city",
        "landmark or infrastructure",
        "satellite sensor",
        "date range",
        "cloud cover threshold",
        "distance measurement"
    ]
    
    entities = model.predict_entities(cleaned, labels, threshold=0.35)

    # 1. Location & Spatial Relation
    spatial_relation = None
    loc_entities = [e for e in entities if e["label"] in ("geographic location or city", "landmark or infrastructure")]
    if loc_entities:
        best_loc = None
        best_geo = None
        for loc_e in loc_entities:
            geo = offline_geocoder.geocode(loc_e["text"])
            if geo:
                best_loc = loc_e["text"]
                best_geo = geo
                break
        if not best_loc:
            best_loc = loc_entities[0]["text"]
            best_geo = offline_geocoder.geocode(best_loc)

        res_name = best_geo["name"] if best_geo else best_loc.title()

        dist_val = 3.0
        rel_type = "near"
        
        dist_match = re.search(r"\b(?:within|inside|at\s+most)\s+(\d+(?:\.\d+)?)\s*(?:km|kilometers|m|meters)?\b", cleaned, re.IGNORECASE)
        if dist_match:
            dist_val = float(dist_match.group(1))
            rel_type = "within"
        elif re.search(r"\b(?:near|close to|along|beside|adjacent to|around|in)\b", cleaned, re.IGNORECASE):
            rel_type = "near"

        spatial_relation = SpatialConstraint(
            relation_type=rel_type,
            target=best_loc,
            distance_km=dist_val,
            resolved_feature_name=res_name
        )
        explanation.append(f"GLiNER extracted location: {best_loc} (Resolved: {res_name}, Proximity: {rel_type} {dist_val}km)")

    # 2. Satellite Sensor
    sensor = None
    sensor_entities = [e for e in entities if e["label"] == "satellite sensor"]
    if sensor_entities:
        sensor = normalize_sensor(sensor_entities[0]["text"])
        explanation.append(f"GLiNER extracted sensor: {sensor}")
    else:
        if re.search(r"\b(sentinel[\s-]?2|s2)\b", cleaned, re.IGNORECASE):
            sensor = "Sentinel-2"
            explanation.append("Extracted sensor: Sentinel-2")
        elif re.search(r"\b(sentinel[\s-]?1|s1)\b", cleaned, re.IGNORECASE):
            sensor = "Sentinel-1"
            explanation.append("Extracted sensor: Sentinel-1")
        elif re.search(r"\b(landsat[\s-]?8|landsat|l8)\b", cleaned, re.IGNORECASE):
            sensor = "Landsat-8"
            explanation.append("Extracted sensor: Landsat-8")

    # 3. Cloud cover constraint
    max_cloud = None
    cloud_match = re.search(r"cloud(?:y| cover)?\s*(?:<|less than|under|below|max)\s*(\d+)%?", cleaned, re.IGNORECASE)
    if cloud_match:
        max_cloud = float(cloud_match.group(1)) / 100.0
        explanation.append(f"Filtered maximum cloud cover to {int(max_cloud * 100)}%")
    elif re.search(r"(?:excluding|without|no)\s+cloudy(?:\s+imagery)?", cleaned, re.IGNORECASE):
        max_cloud = 0.15
        explanation.append("Excluded cloudy imagery (max cloud < 15%)")
    elif re.search(r"clear\s+sky(?:\s+only)?", cleaned, re.IGNORECASE):
        max_cloud = 0.10
        explanation.append("Enforced clear sky filter (max cloud < 10%)")

    # 4. Date ranges
    date_from = None
    date_to = None
    after_match = re.search(r"\b(?:after|since|from|post)\s+([a-zA-Z]+)?\s*(\d{4})(?:-(\d{2})-(\d{2}))?\b", cleaned, re.IGNORECASE)
    if after_match:
        month_str, year_str, m_num, d_num = after_match.group(1), after_match.group(2), after_match.group(3), after_match.group(4)
        if m_num and d_num:
            date_from = f"{year_str}-{m_num}-{d_num}"
        elif month_str and month_str.lower() in MONTH_MAP:
            date_from = f"{year_str}-{MONTH_MAP[month_str.lower()]}-01"
        else:
            date_from = f"{year_str}-01-01"
        explanation.append(f"Applied date lower-bound: >= {date_from}")

    before_match = re.search(r"\b(?:before|until|to|prior to)\s+([a-zA-Z]+)?\s*(\d{4})(?:-(\d{2})-(\d{2}))?\b", cleaned, re.IGNORECASE)
    if before_match:
        month_str, year_str, m_num, d_num = before_match.group(1), before_match.group(2), before_match.group(3), before_match.group(4)
        if m_num and d_num:
            date_to = f"{year_str}-{m_num}-{d_num}"
        elif month_str and month_str.lower() in MONTH_MAP:
            date_to = f"{year_str}-{MONTH_MAP[month_str.lower()]}-28"
        else:
            date_to = f"{year_str}-12-31"
        explanation.append(f"Applied date upper-bound: <= {date_to}")

    # 5. Extract Core Semantic Query
    sem_text = cleaned
    if after_match:
        sem_text = sem_text.replace(after_match.group(0), " ")
    if before_match:
        sem_text = sem_text.replace(before_match.group(0), " ")
    if cloud_match:
        sem_text = sem_text.replace(cloud_match.group(0), " ")
    sem_text = re.sub(r"(?:excluding|without|no)\s+cloudy(?:\s+imagery)?", " ", sem_text, flags=re.IGNORECASE)
    sem_text = re.sub(r"clear\s+sky(?:\s+only)?", " ", sem_text, flags=re.IGNORECASE)
    
    # Remove all location entities
    for loc_e in loc_entities:
        sem_text = re.sub(re.escape(loc_e["text"]), " ", sem_text, flags=re.IGNORECASE)
    # Remove all sensor entities
    for s_e in sensor_entities:
        sem_text = re.sub(re.escape(s_e["text"]), " ", sem_text, flags=re.IGNORECASE)
    # Also strip sensor keywords if missed
    sem_text = re.sub(r"\b(sentinel[\s-]?[12]|sar|landsat[\s-]?8|liss[\s-]?[34]|awifs)\b", " ", sem_text, flags=re.IGNORECASE)

    # Remove distance expressions like "within 5km of", "within 5 km"
    sem_text = re.sub(r"\b(?:within|inside|at\s+most)\s+(\d+(?:\.\d+)?)\s*(?:km|kilometers|m|meters)?(?:\s+of)?\b", " ", sem_text, flags=re.IGNORECASE)
    sem_text = re.sub(r"\b\d+(\.\d+)?\s*(km|kilometers|m|meters)\b", " ", sem_text, flags=re.IGNORECASE)
    # Clean dangling spatial prepositions & conjunctions
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

if __name__ == "__main__":
    queries = [
        "New buildings near Hooghly river in Kolkata after 2024 with cloud < 10% on Sentinel-2",
        "Flooded agricultural land in Rajarhat Action Area on Sentinel-1 SAR since September 2024",
        "Dense urban expansion along EM Bypass in Salt Lake Sector 5",
        "water bodies and rivers within 5km of Biswa Bangla Gate with clear sky",
        "deforestation and illegal logging near Sundarbans before 2023 on Landsat-8",
        "industrial warehouses near Kolkata Port"
    ]

    print("Benchmarking parse_with_gliner()...\n")
    for q in queries:
        t0 = time.perf_counter()
        parsed = parse_with_gliner(q)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"Query: '{q}' ({elapsed_ms:.1f} ms)")
        print(f"  -> Semantic Query: '{parsed.semantic_query}'")
        print(f"  -> Spatial: {parsed.spatial_relation}")
        print(f"  -> Sensor: {parsed.sensor}")
        print(f"  -> Date From: {parsed.date_from}, To: {parsed.date_to}")
        print(f"  -> Max Cloud: {parsed.max_cloud_cover}")
        print(f"  -> Explanation: {parsed.explanation}")
        print("-" * 60)
