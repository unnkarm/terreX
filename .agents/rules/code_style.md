# TerreX Code Rules

## Offline-First (Non-Negotiable)
- Zero runtime cloud API calls. No OpenAI, Gemini, HuggingFace Hub, Google Maps, or external tile servers.
- All models load from `MODEL_DIR` (`/models` in Docker, `{ROOT}/models` locally).
- Ollama is optional (chat profile only). If unavailable, return 503 gracefully — never pretend it is up.
- `OFFLINE_MODE=true` and `HF_HUB_OFFLINE=1` are always set in Docker.

## Python (Backend — FastAPI + SQLAlchemy)
- Python 3.11+. Type hints on all public functions/methods.
- FastAPI route files: `backend/api/routes_*.py`. Prefix every router with `/api/<domain>`.
- Use `backend/config.py` `Settings` singleton for all env vars. Never call `os.getenv()` in service files directly.
- SQLAlchemy sessions via `db/database.py:get_session()`. ORM models are in `db/models.py`.
- Dual DB: PostGIS (opt-in via `TERREX_USE_POSTGIS=true`) or SQLite (default dev). Never use PostGIS-only functions without the `_USE_POSTGIS` guard.
- Rasterio **windowed reads only** — never load an entire scene into RAM at once.

## TypeScript (Frontend — Next.js App Router)
- `frontend/app/` uses App Router conventions. Check `node_modules/next/dist/docs/` before using new APIs.
- All API calls must go through `frontend/lib/api.ts`. Never call backend URL directly in components.
- MapLibre GL: only local tile sources. No Mapbox tokens, no external tile URLs at runtime.
- Components: `frontend/components/`. Pages/routes: `frontend/app/`.

## AI Model Placeholder Contract
- RemoteCLIP not staged ? set `is_placeholder=True` on every embedding result. Never omit.
- Prithvi-EO not staged ? tag results with `is_placeholder_model=True`.
- Surface placeholder status in the UI with warning banners and badges. Never hide it.
- Prefer the ONNX export (`models/prithvi/prithvi_int8.onnx`) over the Torch checkpoint when ONNX Runtime is available.

## Data Provenance
- Every ingested GeoTIFF must have a `.provenance.json` sidecar. See `scripts/acquisition_common.py` for required fields.
- Valid `source_portal` values: `Bhoonidhi`, `Bhuvan`, `Copernicus Data Space Ecosystem`, `Google Earth Engine`, `USGS EarthExplorer`.

## Testing
- Tests live in `tests/`. Run with: `pytest tests/`
- Keep tests offline — no live satellite API calls. Use `scripts/generate_sample_data.py` for synthetic imagery.
