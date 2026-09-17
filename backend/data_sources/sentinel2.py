"""
Sentinel-2 Level-2A Data Adapter.

Primary ML dataset for TerreX:
- 10m resolution for Blue (B02), Green (B03), Red (B04), NIR (B08)
- 20m resolution for SWIR1 (B11), SWIR2 (B12), SCL (Scene Classification Layer)
- Supports windowed streaming via Microsoft Planetary Computer or AWS STAC
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from data_sources.base import BaseEODataSource, EOSearchResult

logger = logging.getLogger("terrex.data_sources.sentinel2")


class Sentinel2DataSource(BaseEODataSource):
    provider_id = "sentinel2"
    provider_name = "Sentinel-2 Level-2A (ESA / Open Access)"
    description = "10m multispectral imagery (B02/B03/B04/B08/B11/B12). Primary high-frequency dataset for TerreX."

    STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"

    def search(
        self,
        bbox_wgs84: List[float],
        start_date: str,
        end_date: str,
        max_cloud_cover: float = 20.0,
        limit: int = 10,
    ) -> List[EOSearchResult]:
        # Runtime is air-gapped.  Sentinel-2 acquisition is performed only by
        # scripts/acquire_sentinel2.py through Bhoonidhi before the demo.
        logger.info("Offline runtime: Sentinel-2 catalog search is disabled")
        return []

    def stage_to_cog(
        self,
        item: EOSearchResult,
        output_dir: Path,
        target_bbox: Optional[List[float]] = None,
    ) -> Path:
        raise RuntimeError(
            "Sentinel-2 staging is disabled in the air-gapped runtime. "
            "Run scripts/acquire_sentinel2.py in the separated acquisition environment."
        )
