"""Runtime descriptor for the acquisition-only ISRO/Bhoonidhi source.

Network acquisition is intentionally confined to ``scripts/acquire_isro.py``.
The serving process never returns a fabricated catalog or raster.
"""
from pathlib import Path
from typing import List, Optional

from data_sources.base import BaseEODataSource, EOSearchResult


class BhuvanDataSource(BaseEODataSource):
    provider_id = "isro-bhuvan"
    provider_name = "ISRO / NRSC Bhoonidhi (acquisition-time only)"
    description = "Stage real Indian EO products with scripts/acquire_isro.py, then ingest locally with provenance."

    def search(
        self,
        bbox_wgs84: List[float],
        start_date: str,
        end_date: str,
        max_cloud_cover: float = 20.0,
        limit: int = 10,
    ) -> List[EOSearchResult]:
        return []

    def stage_to_cog(
        self,
        item: EOSearchResult,
        output_dir: Path,
        target_bbox: Optional[List[float]] = None,
    ) -> Path:
        raise RuntimeError(
            "Bhoonidhi staging is disabled in the air-gapped runtime. "
            "Run scripts/acquire_isro.py in the separated acquisition environment."
        )
