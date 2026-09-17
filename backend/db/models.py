"""
SQLAlchemy ORM models for TerreX metadata store.

Dual-mode design:
  - Production: PostgreSQL + PostGIS — geometry columns use GeoAlchemy2 types.
    The PostGIS path is opt-in via the TERREX_USE_POSTGIS=true env var.
  - Development / local demo: SQLite — geometry stored as plain WKT Text.
    This is the default when PostgreSQL is not available.

We deliberately never import geoalchemy2 unless explicitly opted in, because
importing it at all registers a global SQLAlchemy compile hook that wraps every
geometry column in AsEWKB() — a PostGIS-only function that raises
sqlite3.OperationalError on SQLite.
"""
import os
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, DateTime, ForeignKey, JSON, Boolean, Text
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Opt-in PostGIS path — only activated by explicit env var *and* when
# geoalchemy2 + psycopg2 are installed.
_USE_POSTGIS = os.getenv("TERREX_USE_POSTGIS", "false").strip().lower() in ("1", "true", "yes")
_PostGISGeom = None
_PGUUIDType = None

if _USE_POSTGIS:
    try:
        from geoalchemy2 import Geometry as _Geometry
        from sqlalchemy.dialects.postgresql import UUID as _PGUUID
        _PostGISGeom = _Geometry
        _PGUUIDType = _PGUUID(as_uuid=False)
    except ImportError:
        _USE_POSTGIS = False


def _geom_col(nullable: bool = True):
    """Return a geometry Column, using PostGIS type or plain WKT Text."""
    if _USE_POSTGIS and _PostGISGeom is not None:
        return Column(_PostGISGeom(geometry_type="POLYGON", srid=4326), nullable=nullable)
    return Column(Text, nullable=nullable)


def _uuid_type():
    """Return the appropriate UUID column type."""
    if _USE_POSTGIS and _PGUUIDType is not None:
        return _PGUUIDType
    return String


def gen_uuid():
    return str(uuid.uuid4())


class Scene(Base):
    """A single ingested GeoTIFF/COG — the unit of provenance."""
    __tablename__ = "scenes"

    scene_id = Column(_uuid_type(), primary_key=True, default=gen_uuid)
    source_filename = Column(String, nullable=False)
    source_path = Column(String, nullable=False)

    sensor = Column(String, nullable=True)
    acquisition_date = Column(DateTime, nullable=True)
    resolution_m = Column(Float, nullable=True)
    crs = Column(String, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    band_count = Column(Integer, nullable=True)

    cloud_fraction = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    valid_pixel_fraction = Column(Float, nullable=True)

    footprint = _geom_col(nullable=True)

    processing_version = Column(String, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="ingested")  # ingested | quarantined | failed
    status_reason = Column(Text, nullable=True)
    source_hash = Column(String, nullable=True, index=True)
    source_portal = Column(String, nullable=True)
    underlying_dataset = Column(String, nullable=True)
    cloud_cover_pct = Column(Float, nullable=True)
    license_source = Column(String, nullable=True)
    cog_validation = Column(JSON, nullable=True)
    provenance = Column(JSON, nullable=True)

    tiles = relationship("Tile", back_populates="scene", cascade="all, delete-orphan")


class Tile(Base):
    """A tile cut from a scene — the unit of embedding + search."""
    __tablename__ = "tiles"

    tile_id = Column(_uuid_type(), primary_key=True, default=gen_uuid)
    scene_id = Column(_uuid_type(), ForeignKey("scenes.scene_id"), nullable=False)

    row_off = Column(Integer, nullable=False)
    col_off = Column(Integer, nullable=False)
    tile_size = Column(Integer, nullable=False)

    lon = Column(Float, nullable=False)
    lat = Column(Float, nullable=False)
    geometry = _geom_col(nullable=False)

    acquisition_date = Column(DateTime, nullable=True)
    sensor = Column(String, nullable=True)
    resolution_m = Column(Float, nullable=True)
    crs = Column(String, nullable=True)

    cloud_fraction = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)

    thumbnail_path = Column(String, nullable=True)
    tile_path = Column(String, nullable=True)

    embedding = Column(JSON, nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_is_placeholder = Column(Boolean, default=False)

    processing_version = Column(String, nullable=False)
    quality_mask_path = Column(String, nullable=True)
    clear_fraction = Column(Float, nullable=True)
    quality_mask_summary = Column(JSON, nullable=True)
    radiometric_stats = Column(JSON, nullable=True)
    spectral_indices = Column(JSON, nullable=True)
    provenance = Column(JSON, nullable=True)
    embedding_model_version = Column(String, nullable=True)

    scene = relationship("Scene", back_populates="tiles")


class ChangeResult(Base):
    """Cached change-detection result for an AOI + date pair."""
    __tablename__ = "change_results"

    change_id = Column(_uuid_type(), primary_key=True, default=gen_uuid)
    before_tile_id = Column(_uuid_type(), ForeignKey("tiles.tile_id"), nullable=False)
    after_tile_id = Column(_uuid_type(), ForeignKey("tiles.tile_id"), nullable=False)

    change_score = Column(Float, nullable=False)
    quality_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    change_area_m2 = Column(Float, nullable=True)
    change_mask_path = Column(String, nullable=True)

    reasons = Column(JSON, nullable=True)
    method = Column(String, nullable=False)
    is_placeholder_model = Column(Boolean, default=False)
    analysis_key = Column(String, nullable=True, index=True)
    earliest_supported_observation = Column(DateTime, nullable=True)
    confirmed_observation = Column(DateTime, nullable=True)
    temporal_uncertainty_days = Column(Float, nullable=True)
    persistence_status = Column(String, nullable=True)
    persistence_log = Column(JSON, nullable=True)
    observations = Column(JSON, nullable=True)
    evidence = Column(JSON, nullable=True)
    registration = Column(JSON, nullable=True)
    dominant_change_type = Column(String, nullable=True)
    dominant_dynamics = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    """Analyst confirm/reject feedback."""
    __tablename__ = "feedback"

    feedback_id = Column(_uuid_type(), primary_key=True, default=gen_uuid)
    target_type = Column(String, nullable=False)   # "tile" | "change_result"
    target_id = Column(_uuid_type(), nullable=False)
    verdict = Column(String, nullable=False)        # "confirm" | "reject"
    analyst = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
