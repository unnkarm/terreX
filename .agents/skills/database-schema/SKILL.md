---
name: database-schema
description: ORM model definitions, dual-database pattern, and query conventions for TerreX. Use this skill when working with Scene, Tile, ChangeResult, or Feedback models, writing SQLAlchemy queries, or understanding the PostgreSQL vs SQLite dual-mode design.
---

# Database Schema

## When to Use
- Writing SQLAlchemy queries against Scene, Tile, ChangeResult, or Feedback
- Adding new columns or relationships to ORM models
- Debugging geometry column errors (PostGIS vs SQLite conflict)

## Dual-Mode Design
- **Dev/default**: SQLite — geometry stored as WKT `Text`
- **Production**: PostgreSQL 16 + PostGIS — `Geometry(POLYGON, srid=4326)`
- Switch: `TERREX_USE_POSTGIS=true`
- **Rule**: Never use PostGIS-only functions (`ST_DWithin`, `AsEWKB`) without the `_USE_POSTGIS` guard in `db/models.py`

## Models (`backend/db/models.py`)

**Scene** — one per ingested GeoTIFF
`scene_id` · `source_filename` · `sensor` · `acquisition_date` · `resolution_m` · `cloud_fraction` · `quality_score` · `footprint` (WKT/geom) · `status` (ingested/quarantined/failed) · `provenance` (JSON) · `source_portal`

**Tile** — many per Scene, unit of embedding + search
`tile_id` · `scene_id FK` · `row_off/col_off` · `lon/lat` · `geometry` · `embedding` (JSON 512-dim) · `embedding_is_placeholder` · `spectral_indices` (JSON) · `thumbnail_path` · `quality_score` · `cloud_fraction`

**ChangeResult** — cached change output
`change_id` · `before_tile_id FK` · `after_tile_id FK` · `change_score` · `confidence` · `is_placeholder_model` · `dominant_change_type` · `dominant_dynamics` · `evidence` (JSON) · `persistence_status` · `analysis_key` (indexed)

**Feedback** — analyst verdict
`feedback_id` · `target_type` (tile/change_result) · `target_id` · `verdict` (confirm/reject) · `analyst` · `note`

## Session Pattern
```python
from db.database import get_session
from db.models import Tile
from sqlalchemy import select

with get_session() as session:
    tiles = session.execute(select(Tile).where(Tile.cloud_fraction < 0.3)).scalars().all()
```
Never create sessions outside `get_session()`. Schema auto-created by `Base.metadata.create_all()` on startup.
