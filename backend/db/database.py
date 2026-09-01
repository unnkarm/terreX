from contextlib import contextmanager
import logging

from sqlalchemy import create_engine
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

from config import settings
from db.models import Base

logger = logging.getLogger("terrex.db")

_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        db_url = settings.DATABASE_URL
        # Fallback to sqlite if postgres is unreachable during standalone test runs
        if "sqlite" in db_url:
            _engine = create_engine(db_url, connect_args={"check_same_thread": False})
        else:
            _engine = create_engine(db_url, pool_pre_ping=True)
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
    Base.metadata.create_all(bind=engine)


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
