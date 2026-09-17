"""Runtime descriptor for acquisition-only MOSDAC products."""
from pathlib import Path
from typing import List, Optional

from data_sources.base import BaseEODataSource, EOSearchResult


class MosdacDataSource(BaseEODataSource):
    provider_id = "isro-mosdac"
    provider_name = "ISRO MOSDAC (acquisition-time only)"
    description = "No runtime network access. Stage verified MOSDAC data externally and ingest it with provenance."

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
            "MOSDAC staging is disabled in the air-gapped runtime. "
            "Stage a real product in the acquisition environment first."
        )
