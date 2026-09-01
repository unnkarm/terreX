"""
TerreX backend configuration.

All configuration is environment-driven so the same image can run in
docker-compose, bare-metal, or CI, and so OFFLINE_MODE can be enforced
at every layer (embeddings, tiles, map data).
"""
import os
from pathlib import Path


def _bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # --- Offline enforcement -------------------------------------------------
    OFFLINE_MODE: bool = _bool("OFFLINE_MODE", "true")

    # --- Paths -----------------------------------------------------------------
    MODEL_DIR: Path = Path(os.getenv("MODEL_DIR", "/models"))
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/data"))
    INCOMING_DIR: Path = DATA_DIR / "incoming"
    SCENES_DIR: Path = DATA_DIR / "scenes"
    TILES_DIR: Path = DATA_DIR / "tiles"

    REMOTECLIP_DIR: Path = MODEL_DIR / "remoteclip"
    PRITHVI_DIR: Path = MODEL_DIR / "prithvi"
    CHANGE_MODEL_DIR: Path = MODEL_DIR / "change"

    # --- Databases ---------------------------------------------------------
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://terrex:terrex@postgres:5432/terrex",
    )
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://qdrant:6333")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "terrex_tiles")

    # --- Tiling / ingestion --------------------------------------------------
    TILE_SIZE: int = int(os.getenv("TILE_SIZE", "256"))
    TILE_OVERLAP: int = int(os.getenv("TILE_OVERLAP", "0"))
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "512"))
    PROCESSING_VERSION: str = os.getenv("PROCESSING_VERSION", "terrex-mvp-0.1.0")

    # --- Ranking weights (Feature 6 — hybrid ranking) ------------------------
    W_SEMANTIC: float = float(os.getenv("W_SEMANTIC", "0.45"))
    W_GEO: float = float(os.getenv("W_GEO", "0.15"))
    W_METADATA: float = float(os.getenv("W_METADATA", "0.10"))
    W_QUALITY: float = float(os.getenv("W_QUALITY", "0.15"))
    W_CHANGE: float = float(os.getenv("W_CHANGE", "0.15"))

    # --- Change detection / false-alarm thresholds --------------------------
    CLOUD_FRACTION_MAX: float = float(os.getenv("CLOUD_FRACTION_MAX", "0.35"))
    MIN_QUALITY_SCORE: float = float(os.getenv("MIN_QUALITY_SCORE", "0.4"))
    CHANGE_PROB_THRESHOLD: float = float(os.getenv("CHANGE_PROB_THRESHOLD", "0.5"))

    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")


settings = Settings()

for p in (settings.INCOMING_DIR, settings.SCENES_DIR, settings.TILES_DIR):
    p.mkdir(parents=True, exist_ok=True)
