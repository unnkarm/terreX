-- Executed automatically by the postgis/postgis image on first container start
-- (mounted into /docker-entrypoint-initdb.d/). Tables themselves are created
-- by SQLAlchemy (db.database.init_db) so schema stays in one place (models.py).
CREATE EXTENSION IF NOT EXISTS postgis;
