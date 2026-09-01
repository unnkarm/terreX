"""
Thin wrapper around Qdrant (self-hosted, local — no cloud dependency).
"""
from __future__ import annotations

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from config import settings

logger = logging.getLogger("terrex.vector_store")


class VectorStore:
    def __init__(self):
        self.client = QdrantClient(url=settings.QDRANT_URL)
        self.collection = settings.QDRANT_COLLECTION
        self._ensure_collection()

    def _ensure_collection(self):
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(
                    size=settings.EMBEDDING_DIM, distance=qm.Distance.COSINE
                ),
            )
            logger.info("Created Qdrant collection '%s'", self.collection)

    def upsert_tile(self, tile_id: str, vector, payload: dict):
        self.client.upsert(
            collection_name=self.collection,
            points=[qm.PointStruct(id=tile_id, vector=vector.tolist(), payload=payload)],
        )

    def delete_tile(self, tile_id: str):
        self.client.delete(
            collection_name=self.collection,
            points_selector=qm.PointIdsList(points=[tile_id]),
        )

    def search(
        self,
        vector,
        top_k: int = 20,
        sensor: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        min_similarity: float = 0.0,
        aoi_bbox: Optional[tuple] = None,  # (min_lon, min_lat, max_lon, max_lat)
    ):
        must = []
        if sensor:
            must.append(qm.FieldCondition(key="sensor", match=qm.MatchValue(value=sensor)))
        if date_from or date_to:
            rng = {}
            if date_from:
                rng["gte"] = date_from
            if date_to:
                rng["lte"] = date_to
            must.append(qm.FieldCondition(key="acquisition_date", range=qm.DatetimeRange(**rng)))
        if aoi_bbox:
            min_lon, min_lat, max_lon, max_lat = aoi_bbox
            must.append(qm.FieldCondition(key="lon", range=qm.Range(gte=min_lon, lte=max_lon)))
            must.append(qm.FieldCondition(key="lat", range=qm.Range(gte=min_lat, lte=max_lat)))

        query_filter = qm.Filter(must=must) if must else None

        hits = self.client.search(
            collection_name=self.collection,
            query_vector=vector.tolist(),
            query_filter=query_filter,
            limit=top_k,
            score_threshold=min_similarity if min_similarity > 0 else None,
        )
        return hits


vector_store = VectorStore()
