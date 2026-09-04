# TerreX — Offline AI Satellite Intelligence Platform

An offline, AI-powered satellite imagery search and change-detection MVP.
Analysts can search imagery in natural language or by reference image,
filter by location/date/sensor, view ranked results on a map, compare
imagery across dates, detect meaningful change with false-alarm
suppression, and confirm/reject findings — all without any runtime network
dependency.

## Status: what's real vs. placeholder

This MVP is built so it is **honest about what's real AI and what's wiring**.
Two models are pluggable and expected to be staged locally:

| Component | Real model | Status if not staged |
|---|---|---|
| Semantic embeddings (Feature 2, 3) | RemoteCLIP | Deterministic, non-AI visual/lexical-hash embedder (`is_placeholder=True` on every result) |
| Change-detection features (Feature 4) | Prithvi-EO | Non-AI statistical patch features (mean/std/edge energy), tagged `is_placeholder_model=True` |

The backend, API responses, and frontend UI all surface this status
explicitly (badges, warning banners, `GET /api/system/status`) — nothing
pretends placeholder output is a trained model's output. See
`models/remoteclip/README.md` and `models/prithvi/README.md` for staging
instructions.

The change-detection "head" itself starts as a simple, documented
feature-difference + threshold function regardless of which feature
extractor is active — per the project brief's explicit fallback
instruction. It's isolated in one function so a trained head can replace
it later without touching the rest of the pipeline.

## Architecture

```
Frontend (Next.js + MapLibre)
   ↓ REST
FastAPI Backend
   ↓
AI/ML: RemoteCLIP (embeddings) · Prithvi-EO (EO features) · feature-diff change head
   ↓                    ↓
Qdrant (vectors)     PostgreSQL + PostGIS (metadata, geometry, provenance)
   ↓                    ↓
data/scenes, data/tiles (imagery + thumbnails on disk)
```

AI inference runs in-process inside the backend container — no separate
inference microservice, per the "keep it simple" constraint.

## Quick start

```bash
cp .env.example .env
docker compose build
docker compose up -d
```

Then generate the offline demo dataset and ingest it:

```bash
# from the repo root, using a Python env with the backend's requirements installed
pip install -r backend/requirements.txt
python scripts/generate_sample_data.py     # writes synthetic GeoTIFFs to data/incoming/
python scripts/ingest.py                    # ingests everything in data/incoming/
```

Or trigger ingestion via the running API / UI "Ingest new imagery" button,
which calls `POST /api/ingest/process-incoming` — this scans `data/incoming/`
for files not already indexed and adds them incrementally (Feature 9), no
full rebuild required.

Open the dashboard at `http://localhost:3000`. The backend API is at
`http://localhost:8000` (interactive docs at `http://localhost:8000/docs`).

Chat uses the optional local Ollama service in the `chat` Compose profile.
Before disconnecting the machine from the internet, preload the image and the
configured model on that machine, for example with `docker pull
ollama/ollama:latest`, then `docker compose --profile chat up -d ollama` and
`docker exec terrex-ollama ollama pull qwen2.5:1.5b-instruct-q4_K_M`.
Runtime chat makes no cloud calls. If the profile, image, or model is not
staged, the API reports chat as unavailable rather than pretending it is
operational. The default `docker compose up -d` remains usable offline without
the optional chat image.

The Compose backend installs the real RemoteCLIP/Prithvi runtime dependencies.
Stage the licensed weights before starting it; model files are intentionally
ignored by Git. The provided staging script verifies SHA-256 checksums against
the upstream releases:

```bash
python scripts/stage_models.py
```

For a host-only backend, install `backend/requirements-ml.txt` as well. Once
models are staged, re-ingest scenes that include B02, B03, B04, NIR, SWIR1,
and SWIR2; legacy six-band files ending in SCL continue through the clearly
labelled statistical fallback.

Try a query like `new buildings near a river`, then click a result and run
**Detect changes** between `2023-01-01` and `2024-01-01` — the synthetic
demo scene includes a settlement that visibly grows over that window, plus
one cloud-contaminated observation to demonstrate false-alarm suppression.

## Demo dataset

Since this environment has no access to real satellite archives at
runtime, `scripts/generate_sample_data.py` produces small, **geospatially
valid** synthetic GeoTIFFs (real CRS, real transform/bounds, real GDAL
tags) depicting a river and a settlement that grows across 5 dates, with
one deliberately hazy/cloudy scene. This is clearly a synthetic stand-in
for real imagery, not a simulated AI result — the same ingestion code path
handles real GeoTIFF/COG scenes dropped into `data/incoming/`.

To use real imagery instead: place `.tif`/`.tiff` (ideally Cloud-Optimized
GeoTIFF) files into `data/incoming/` and run `scripts/ingest.py`, or use the
`POST /api/ingest/upload` endpoint.

## Feature map

| # | Feature | Where |
|---|---|---|
| 1 | Ingestion (GeoTIFF/COG → tiles → embeddings → Qdrant/Postgres) | `backend/services/ingestion.py`, `scripts/ingest.py` |
| 2 | Semantic text search | `backend/services/search.py`, `POST/GET /api/search/text` |
| 3 | Image-to-image search | `backend/services/search.py`, `POST /api/search/image` |
| 4 | Change detection | `backend/services/change_detection.py`, `GET /api/change/detect` |
| 5 | False-alarm suppression | `backend/services/false_alarm.py` |
| 6 | Hybrid ranking | `backend/services/ranking.py` |
| 7 | Analyst dashboard + feedback | `frontend/`, `backend/api/routes_feedback.py` |
| 9 | Incremental ingestion | `POST /api/ingest/process-incoming` (skips already-indexed filenames) |

## Offline guarantees

- `OFFLINE_MODE=true` is set by default; the backend logs this at startup.
- No code path calls the OpenAI/Gemini APIs, a cloud vector DB, Google Maps,
  or the Hugging Face Hub at runtime. Models are loaded only from local
  paths under `MODEL_DIR` (`/models`).
- Qdrant and PostgreSQL/PostGIS run as local containers with persistent
  volumes — no managed/cloud database is used.
- The map (`frontend/components/MapView.tsx`) uses a local MapLibre style
  with no external tile server configured out of the box, so the app does
  not depend on internet map tiles. **To stage real basemap tiles for a
  demo**, run a local tile server (e.g. `maptiler/tileserver-gl` or
  `klokantech/tileserver-gl`) against an offline MBTiles/PMTiles extract of
  your demo AOI, mount it as another docker-compose service, and point
  `OFFLINE_STYLE.sources` in `MapView.tsx` at it. This is left as a manual
  step since it depends on which region you want tiles for.
- Test offline: `docker compose up -d`, then disable networking on the
  host (e.g. disconnect Wi-Fi / drop the default route) and confirm search,
  change detection, and ingestion of new files in `data/incoming/` all
  still work.

## Models used — name, source, version, license

| Model | Source | Version staged by default | License |
|---|---|---|---|
| RemoteCLIP | `chendelong/RemoteCLIP` (Hugging Face); Liu et al., 2023 | Not staged — placeholder active | Research use (verify current model card) |
| Prithvi-EO | `ibm-nasa-geospatial/Prithvi-EO-*` (Hugging Face); NASA IMPACT & IBM Research | Not staged — placeholder active | Apache 2.0 (verify current model card) |
| Change-detection head | This repo's own simple feature-difference function | N/A (not a pretrained model) | This project's license |

No model weights are bundled in this repository; staging is a manual,
documented step (see `models/*/README.md`) so licensing terms are always
reviewed by whoever deploys TerreX.

## Reproducibility & provenance

Every `Scene` and `Tile` row records `processing_version`
(`PROCESSING_VERSION` env var), `source_filename`/`source_path`, the exact
embedding model name used (`embedding_model`, with `embedding_is_placeholder`),
and quality metrics computed at ingest time. Every `ChangeResult` records
which `before_tile_id`/`after_tile_id` pair it came from, the `method`
used, and a human-readable `reasons` list explaining any suppression or
confidence boost applied — so any result in the UI can be traced back to
its inputs.

## Repository layout

```
sat-intel/
├── frontend/            Next.js + TypeScript + Tailwind + MapLibre dashboard
├── backend/             FastAPI app, services (ingestion/search/change/ranking), DB models
├── models/              Stage RemoteCLIP / Prithvi-EO / change-head weights here (see READMEs)
├── data/                incoming/ (drop new imagery) · scenes/ (ingested originals) · tiles/ (cut tiles + thumbnails)
├── scripts/             generate_sample_data.py · ingest.py · build_index.py
├── docker-compose.yml
└── .env.example
```

## Known MVP limitations

- Tile geo-referencing uses linear interpolation across the scene's WGS84
  bounding box rather than a full per-pixel affine reprojection — adequate
  for demo AOIs, not for scenes crossing large distortions (e.g. near poles
  or spanning many UTM zones).
- Registration-offset estimation (`quality.registration_offset_estimate`)
  is a small brute-force shift search, not a proper feature-based image
  registration (e.g. ORB/SIFT + RANSAC) — fine for the synthetic demo,
  should be upgraded before use on real misaligned imagery.
- No authentication/authorization layer — add one before any multi-user or
  networked deployment.
- The demo basemap has no offline tile source configured by default (see
  "Offline guarantees" above for how to stage one).
