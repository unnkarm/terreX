---
name: docker-devops
description: Docker Compose setup, service layout, RAM limits, local dev workflow, and offline model staging for TerreX. Use this skill when working on Docker config, adding new Compose services, debugging container issues, or understanding the local host-only development setup.
---

# Docker & DevOps

## When to Use
- Modifying `docker-compose.yml` or Dockerfiles
- Debugging a container crash, volume mount issue, or env var problem
- Setting up local dev without Docker
- Pre-staging models or basemap tiles before going offline

## Compose Services

| Service | Container | Port | RAM limit |
|---------|-----------|------|-----------|
| `postgres` | terrex-postgres | 5432 | 384 MB |
| `qdrant` | terrex-qdrant | 6333 | 512 MB |
| `backend` | terrex-backend | 8000 | 4096 MB |
| `frontend` | terrex-frontend | 3000 | 512 MB |
| `ollama` | terrex-ollama | 11434 | 1024 MB (profile: `chat`) |

## Quick Start
```bash
cp .env.example .env && python scripts/stage_models.py
docker compose build && docker compose up -d
python scripts/generate_sample_data.py && python scripts/ingest.py
# UI: http://localhost:3000  |  API docs: http://localhost:8000/docs
```

## Optional Chat Profile
```bash
# Pre-pull before going offline:
docker pull ollama/ollama:latest
docker compose --profile chat up -d ollama
docker exec terrex-ollama ollama pull qwen2.5:1.5b-instruct-q4_K_M
docker compose --profile chat up -d
```

## Host-Only Dev (no Docker)
```bash
# Only needs Qdrant + Postgres via Docker:
docker compose up -d qdrant postgres
pip install -r backend/requirements.txt -r backend/requirements-ml.txt
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm install && npm run dev
# Uses SQLite by default (no TERREX_USE_POSTGIS needed)
```

## Volume Mounts
`./models` ? `/models` (ro) · `./data` ? `/data` · `./backend` ? `/app`

## Useful Debug
```bash
docker compose logs -f backend
docker compose restart backend
docker exec -it terrex-postgres psql -U terrex -d terrex
curl http://localhost:6333/collections/terrex_tiles
```
