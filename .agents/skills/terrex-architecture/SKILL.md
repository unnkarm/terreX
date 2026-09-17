---
name: terrex-architecture
description: Compact architectural map and data-flow reference for TerreX. Use this skill when the user asks about how components connect, where a feature is implemented, or how data flows from satellite imagery through to the analyst UI.
---

# TerreX Architecture

## Overview

Offline AI satellite intelligence platform. No runtime cloud calls - everything runs locally.

```
Browser (Next.js 14 - :3000)
  |  REST/JSON
FastAPI (:8000)   -> main.py wires all routers
  |
  +- RemoteCLIP  -> 512-dim embeddings       (services/embeddings.py)
  +- Prithvi-EO  -> EO patch features        (services/prithvi.py)
  +- GLiNER      -> NLP entity extraction    (services/nlp_filter.py)
  +- Ollama      -> chat (optional profile)  (services/chat_agent.py)
  |
  +- Qdrant (:6333)        vector store - 512-dim tile embeddings
  +- PostgreSQL/PostGIS    metadata, geometry, provenance, feedback
       (SQLite in dev - no TERREX_USE_POSTGIS needed)
  |
  data/scenes/  data/tiles/   -> GeoTIFFs + thumbnails on disk
```

## Feature -> File Map

| # | Feature | Files |
|---|---------|-------|
| 1 | Ingestion | `services/ingestion.py`, `scripts/ingest.py` |
| 2 | Text search | `services/search.py`, `api/routes_search.py` |
| 3 | Image search | `services/search.py` (image branch) |
| 4 | Change detection | `services/change_detection.py`, `services/dense_change_detection.py` |
| 4a | Spectral indices | `services/algorithms/spectral.py` |
| 4b | Co-registration | `services/algorithms/registration.py` |
| 4c | Classification | `services/algorithms/change_classifier.py` |
| 5 | False-alarm suppression | `services/false_alarm.py` |
| 6 | Hybrid ranking | `services/ranking.py` |
| 7 | Analyst dashboard | `frontend/`, `api/routes_feedback.py` |
| 8 | NLP parsing | `services/nlp_filter.py`, `services/offline_geocoder.py` |
| 9 | Incremental ingest | `api/routes_ingest.py` -> `POST /api/ingest/process-incoming` |
| 10 | Chat agent | `services/chat_agent.py`, `api/routes_chat.py` |
| 11 | Offline basemap | `api/routes_basemap.py`, `scripts/download_offline_basemap.py` |

## Knowledge Graph Navigation (Token-Saver)
Prefer graph navigation over grep/directory scans for architectural queries:
- `graphify query "<question>"`: BFS traversal of relationships (~1k tokens)
- `graphify path "<A>" "<B>"`: Shortest dependency path
- `graphify-out/GRAPH_REPORT.md`: God nodes and community hubs

## Operational AOI & Key Config
Lon 87.75-88.65, Lat 21.40-23.60 (West Bengal) enforced by `config.py`.
Vars: `MODEL_DIR`, `DATA_DIR`, `TERREX_USE_POSTGIS`, `QDRANT_URL`, `CHAT_MODEL`, `OFFLINE_MODE=true`