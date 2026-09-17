---
name: terrex-backend-api
description: Complete FastAPI route catalog, service wiring, and request/response contract for the TerreX backend. Use this skill when adding new endpoints, debugging API responses, working on hybrid ranking, Qdrant queries, or understanding how the backend is structured.
---

# TerreX Backend API

## When to Use
- Adding a new FastAPI route or debugging an existing one
- Working on hybrid ranking weights, Qdrant queries, or service logic
- Tracing a request from HTTP ? service ? DB

## Route Catalog (`backend/api/`)

| File | Prefix | Key Endpoints |
|------|--------|---------------|
| `routes_search.py` | `/api/search` | `POST /text`, `POST /image` |
| `routes_change.py` | `/api/change` | `GET /detect`, `GET /results`, `GET /{id}` |
| `routes_ingest.py` | `/api/ingest` | `POST /upload`, `POST /process-incoming` |
| `routes_feedback.py` | `/api/feedback` | `POST /`, `GET /` |
| `routes_review.py` | `/api/review` | `GET /queue`, `POST /confirm`, `POST /reject` |
| `routes_basemap.py` | `/api/basemap` | `GET /tiles/{z}/{x}/{y}`, `GET /style.json` |
| `routes_chat.py` | `/api/chat` | `POST /message`, `GET /status` |
| `routes_system.py` | `/api/system` | `GET /status`, `GET /health` |

Entry point: `backend/main.py` — registers all routers, sets CORS, inits services on startup.

## Service Layer

`embeddings.py` RemoteCLIP · `vector_store.py` Qdrant · `search.py` combined search · `ranking.py` hybrid re-rank · `ingestion.py` tile pipeline · `change_detection.py` orchestrator · `false_alarm.py` suppression · `nlp_filter.py` GLiNER · `offline_geocoder.py` geocode · `chat_agent.py` Ollama

## Hybrid Ranking Formula
```
score = 0.45*semantic + 0.15*geo + 0.10*metadata + 0.15*quality + 0.15*change
```
Weights configurable via env vars `W_SEMANTIC`, `W_GEO`, `W_METADATA`, `W_QUALITY`, `W_CHANGE`.

## Adding a New Route
1. Create `backend/api/routes_<domain>.py` with `APIRouter`
2. Register in `backend/main.py`: `app.include_router(router, prefix="/api/<domain>")`
3. Add service logic in `backend/services/`
4. Write tests in `tests/test_<domain>.py`

## Config Rule
Always use `backend/config.py` Settings singleton. Never call `os.getenv()` directly in service files.
