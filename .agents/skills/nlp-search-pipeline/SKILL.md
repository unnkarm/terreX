---
name: nlp-search-pipeline
description: Complete reference for TerreX natural-language search: GLiNER NLP parsing, offline geocoding, vector search (Qdrant), metadata filtering, and hybrid ranking. Use this skill when working on search features, query parsing, or the offline geocoder.
---

# NLP Search Pipeline

## When to Use
- Working on `nlp_filter.py`, `offline_geocoder.py`, `search.py`, or `vector_store.py`
- Debugging why a query returned wrong results or wrong spatial filtering
- Adding new place names to the gazetteer

## Pipeline
```
Query string
  ? GLiNER NLP (in-process CPU, no Ollama)      nlp_filter.py
      extracts: semantic_query, spatial_relation, date_range, quality_filters, sensor
  ? Offline Geocode place name ? (lon, lat)      offline_geocoder.py
  ? Embed semantic_query (RemoteCLIP 512-dim)    embeddings.py
  ? Qdrant ANN search with payload filters       vector_store.py
  ? PostGIS/Shapely spatial distance filter      search.py
  ? Hybrid re-rank                               ranking.py
  ? Ranked results
```

## ParsedQuery Output
```python
@dataclass
class ParsedQuery:
    semantic_query: str           # for CLIP vector search
    spatial_relation: Optional[SpatialConstraint]  # within/near + distance_km
    date_range: Optional[DateRange]                # date_from, date_to
    quality_filters: QualityFilters                # max_cloud_cover, min_quality
    sensor: Optional[str]         # Sentinel-2 | Sentinel-1 | Landsat-8 | LISS-4
```

## Offline Geocoder
Covers ~200 West Bengal features: Kolkata landmarks, suburbs, rivers (Hooghly, Damodar), roads (NH-12, NH-16), industrial zones (Durgapur, Haldia).
**To add places**: append to `GAZETTEER_POINTS` in `offline_geocoder.py` with `name`, `lon`, `lat`, `zone`, `feature_type`, `keywords`.

## Qdrant Payload Fields
Per point: `tile_id` · `scene_id` · `sensor` · `acquisition_date` · `cloud_fraction` · `quality_score` · `lon` · `lat`
Collection: `terrex_tiles` (512-dim, configurable via `QDRANT_COLLECTION`)

## Image Search
`POST /api/search/image` (multipart) ? crop ? RemoteCLIP image encoder ? same Qdrant pipeline. Skips GLiNER step.
