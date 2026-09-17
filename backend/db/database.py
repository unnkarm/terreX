from contextlib import contextmanager
import logging

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

try:
    import psycopg2.extensions
    import numpy as np

    psycopg2.extensions.register_adapter(np.float64, lambda val: psycopg2.extensions.Float(float(val)))
    psycopg2.extensions.register_adapter(np.float32, lambda val: psycopg2.extensions.Float(float(val)))
    psycopg2.extensions.register_adapter(np.int64, lambda val: psycopg2.extensions.Int(int(val)))
    psycopg2.extensions.register_adapter(np.int32, lambda val: psycopg2.extensions.Int(int(val)))
    psycopg2.extensions.register_adapter(np.int16, lambda val: psycopg2.extensions.Int(int(val)))
    psycopg2.extensions.register_adapter(np.uint16, lambda val: psycopg2.extensions.Int(int(val)))
    psycopg2.extensions.register_adapter(np.uint32, lambda val: psycopg2.extensions.Int(int(val)))
    psycopg2.extensions.register_adapter(np.uint64, lambda val: psycopg2.extensions.Int(int(val)))
    psycopg2.extensions.register_adapter(np.bool_, lambda val: psycopg2.extensions.Boolean(bool(val)))
except Exception:
    pass

from sqlalchemy.pool import NullPool
from config import settings
from db.models import Base

logger = logging.getLogger("terrex.db")

_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        db_url = settings.DATABASE_URL
        if "sqlite" in db_url:
            _engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                poolclass=NullPool,
            )
        else:
            try:
                temp_engine = create_engine(
                    db_url,
                    pool_pre_ping=True,
                    pool_size=20,
                    max_overflow=30,
                    pool_timeout=60.0,
                    pool_recycle=1800,
                )
                with temp_engine.connect() as conn:
                    pass
                _engine = temp_engine
            except Exception as exc:
                sqlite_path = (settings.ROOT_DIR / "terrex.db").resolve()
                logger.warning("PostgreSQL unreachable (%s). Falling back to SQLite %s", exc, sqlite_path)
                sqlite_url = f"sqlite:///{sqlite_path.as_posix()}"
                settings.DATABASE_URL = sqlite_url
                _engine = create_engine(
                    sqlite_url,
                    connect_args={"check_same_thread": False},
                    poolclass=NullPool,
                )

        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal


def init_db():
    """Create the PostGIS extension (if missing) and all tables."""
    engine = get_engine()
    if "postgres" in settings.DATABASE_URL:
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis;")
                conn.commit()
        except Exception as exc:
            logger.warning("Could not execute CREATE EXTENSION postgis: %s", exc)

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        if "sqlite" in str(engine.url):
            logger.warning("SQLite DDL event warning (ignoring SpatiaLite geometry hook error): %s", exc)
        else:
            raise exc
    _ensure_ingestion_schema(engine)


def _ensure_ingestion_schema(engine):
    """Add v2 ingestion columns for databases created by an older checkout."""
    additions = {
        "scenes": {
            "source_hash": "VARCHAR", "source_portal": "VARCHAR", "underlying_dataset": "VARCHAR",
            "cloud_cover_pct": "FLOAT", "license_source": "VARCHAR", "cog_validation": "JSON",
            # provenance was added to the ORM model after initial schema creation
            "provenance": "JSON",
        },
        "tiles": {
            "quality_mask_path": "VARCHAR", "clear_fraction": "FLOAT", "quality_mask_summary": "JSON",
            "radiometric_stats": "JSON", "spectral_indices": "JSON", "provenance": "JSON",
            "embedding_model_version": "VARCHAR",
            "embedding": "JSON", "embedding_model": "VARCHAR", "embedding_is_placeholder": "BOOLEAN DEFAULT FALSE",
        },
        "change_results": {
            # Multi-evidence pipeline provenance, added with the evidence-fusion detector.
            "evidence_layers": "JSON", "pipeline_stages": "JSON",
            "analysis_key": "VARCHAR",
            "earliest_supported_observation": "TIMESTAMP",
            "confirmed_observation": "TIMESTAMP",
            "temporal_uncertainty_days": "FLOAT",
            "persistence_status": "VARCHAR",
            "persistence_log": "JSON",
            "observations": "JSON",
            "evidence": "JSON",
            "registration": "JSON",
            "dominant_change_type": "VARCHAR",
            "dominant_dynamics": "VARCHAR",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table)} if inspector.has_table(table) else set()
            for name, sql_type in columns.items():
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


@contextmanager
def get_session():
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    """FastAPI dependency."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
