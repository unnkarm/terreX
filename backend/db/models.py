"""
SQLAlchemy ORM models for TerreX metadata store (PostgreSQL + PostGIS).

Two core tables:
  - scenes: one row per source GeoTIFF/COG (full provenance)
  - tiles:  one row per tile cut from a scene (unit of search / indexing)

A `feedback` table stores analyst confirm/reject actions (Feature 7).
A `change_results` table stores computed change-detection results so they
don't need to be recomputed for every request.
"""
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, ForeignKey, JSON, Boolean, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


class Scene(Base):
    """A single ingested GeoTIFF/COG — the unit of provenance."""
    __tablename__ = "scenes"

    scene_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
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

    footprint = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)

    processing_version = Column(String, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="ingested")  # ingested | quarantined | failed
    status_reason = Column(Text, nullable=True)
    source_hash = Column(String, nullable=True, index=True)
    license_source = Column(String, nullable=True)
    cog_validation = Column(JSON, nullable=True)

    tiles = relationship("Tile", back_populates="scene", cascade="all, delete-orphan")


class Tile(Base):
    """A tile cut from a scene — the unit of embedding + search."""
    __tablename__ = "tiles"

    tile_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    scene_id = Column(UUID(as_uuid=False), ForeignKey("scenes.scene_id"), nullable=False)

    row_off = Column(Integer, nullable=False)
    col_off = Column(Integer, nullable=False)
    tile_size = Column(Integer, nullable=False)

    lon = Column(Float, nullable=False)
    lat = Column(Float, nullable=False)
    geometry = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)

    acquisition_date = Column(DateTime, nullable=True)
    sensor = Column(String, nullable=True)
    resolution_m = Column(Float, nullable=True)
    crs = Column(String, nullable=True)

    cloud_fraction = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)

    thumbnail_path = Column(String, nullable=True)
    tile_path = Column(String, nullable=True)

    embedding_model = Column(String, nullable=True)  # e.g. "remoteclip-v1" / "placeholder-hash"
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

    change_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    before_tile_id = Column(UUID(as_uuid=False), ForeignKey("tiles.tile_id"), nullable=False)
    after_tile_id = Column(UUID(as_uuid=False), ForeignKey("tiles.tile_id"), nullable=False)

    change_score = Column(Float, nullable=False)       # raw model/feature-diff signal
    quality_score = Column(Float, nullable=False)       # combined quality of both obs
    confidence = Column(Float, nullable=False)          # final, after suppression
    change_area_m2 = Column(Float, nullable=True)
    change_mask_path = Column(String, nullable=True)

    reasons = Column(JSON, nullable=True)               # list[str] explaining suppression/boost
    method = Column(String, nullable=False)             # "prithvi-diff" | "feature-diff-placeholder"
    is_placeholder_model = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    """Analyst confirm/reject feedback (Feature 7)."""
    __tablename__ = "feedback"

    feedback_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    target_type = Column(String, nullable=False)   # "tile" | "change_result"
    target_id = Column(UUID(as_uuid=False), nullable=False)
    verdict = Column(String, nullable=False)        # "confirm" | "reject"
    analyst = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
