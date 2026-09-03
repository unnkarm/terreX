from __future__ import annotations

from typing import Dict, List, Optional
from data_sources.base import BaseEODataSource, EOSearchResult
from data_sources.sentinel2 import Sentinel2DataSource
from data_sources.bhuvan import BhuvanDataSource
from data_sources.mosdac import MosdacDataSource

DATA_SOURCES: Dict[str, BaseEODataSource] = {
    "sentinel2": Sentinel2DataSource(),
    "isro-bhuvan": BhuvanDataSource(),
    "isro-mosdac": MosdacDataSource(),
}


def get_data_source(provider_id: str) -> Optional[BaseEODataSource]:
    return DATA_SOURCES.get(provider_id)


def list_available_sources() -> List[Dict[str, str]]:
    return [
        {
            "id": src.provider_id,
            "name": src.provider_name,
            "description": src.description,
            "role": "Primary ML" if src.provider_id == "sentinel2" else "Indian EO National Archive",
        }
        for src in DATA_SOURCES.values()
    ]
