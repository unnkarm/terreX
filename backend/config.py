"""
TerreX backend configuration.

All configuration is environment-driven with automatic .env file loading
(via python-dotenv). Works seamlessly both inside Docker containers and
when running locally on host machine.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from root directory first, then backend directory (backend takes precedence)
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


def _bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # --- Offline enforcement -------------------------------------------------
    OFFLINE_MODE: bool = _bool("OFFLINE_MODE", "true")

    # --- Paths (smart detection: uses local project dirs if container dirs don't exist) ---
    # ROOT_DIR is the project root (parent of backend/). In Docker, /models and /data
    # are mounted; locally we fall back to ROOT_DIR/models and ROOT_DIR/data.
    # Any relative path from the .env is resolved relative to ROOT_DIR so the backend
    # finds the right directory regardless of which CWD uvicorn was started from.
    _default_model_dir = str(ROOT_DIR / "models") if not Path("/models").exists() else "/models"
    _default_data_dir = str(ROOT_DIR / "data") if not Path("/data").exists() else "/data"

    def _resolve_dir(env_var: str, default: str) -> Path:
        """Resolve a directory path. Relative paths are resolved against ROOT_DIR."""
        raw = os.getenv(env_var, default)
        p = Path(raw)
        if p.is_absolute():
            return p.resolve()
        # Relative path — strip any leading ../ and resolve from project root
        # e.g. '../models' or './models' or 'models' all map to ROOT_DIR/models
        parts = [part for part in p.parts if part not in ("..", ".")]
        if parts:
            return (ROOT_DIR / Path(*parts)).resolve()
        # Fallback to default
        return Path(default).resolve()

    MODEL_DIR: Path = _resolve_dir("MODEL_DIR", _default_model_dir)
    DATA_DIR: Path = _resolve_dir("DATA_DIR", _default_data_dir)
    INCOMING_DIR: Path = DATA_DIR / "incoming"
    SCENES_DIR: Path = DATA_DIR / "scenes"
    TILES_DIR: Path = DATA_DIR / "tiles"

    REMOTECLIP_DIR: Path = MODEL_DIR / "remoteclip"
    PRITHVI_DIR: Path = MODEL_DIR / "prithvi"
    CHANGE_MODEL_DIR: Path = MODEL_DIR / "change"

    # --- Databases (defaults to localhost for host development, overridden in Docker) ---
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://terrex:terrex@localhost:5432/terrex",
    )
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
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
