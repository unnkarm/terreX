"""
Base interface for Indian and Global Earth Observation (EO) data providers.

All sources (Sentinel-2, ISRO/NRSC Bhuvan, ISRO MOSDAC) implement this interface.
Their output is normalized to a common multi-band Cloud-Optimized GeoTIFF (COG)
format so TerreX's core intelligence engine (RemoteCLIP, Qdrant, PostGIS,
and Spectral Change Engine) works seamlessly without caring where the data originated.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class EOSearchResult:
    item_id: str
    provider: str  # "sentinel-2" | "isro-bhuvan" | "isro-mosdac"
    dataset_name: str
    acquisition_date: datetime
    cloud_cover_percent: Optional[float]
    bbox_wgs84: List[float]  # [min_lon, min_lat, max_lon, max_lat]
    spatial_resolution_m: float
    bands: List[str]
    download_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BaseEODataSource(ABC):
    provider_id: str
    provider_name: str
    description: str

    @abstractmethod
    def search(
        self,
        bbox_wgs84: List[float],
        start_date: str,
        end_date: str,
        max_cloud_cover: float = 20.0,
        limit: int = 10,
    ) -> List[EOSearchResult]:
        """Search available scenes from this EO provider matching spatial and temporal criteria."""
        pass

    @abstractmethod
    def stage_to_cog(
        self,
        item: EOSearchResult,
        output_dir: Path,
        target_bbox: Optional[List[float]] = None,
    ) -> Path:
        """
        Fetch or convert provider scene data into a normalized multi-band GeoTIFF/COG
        and save it into the TerreX incoming archive directory.
        """
        pass
