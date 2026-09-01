"""
Thin wrapper around Qdrant (self-hosted, local — no cloud dependency).
Configured with on-disk storage and INT8 scalar quantization to respect the 4GB RAM ceiling.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from config import settings

logger = logging.getLogger("terrex.vector_store")


class VectorStore:
    def __init__(self):
        self.client = QdrantClient(url=settings.QDRANT_URL, check_compatibility=False)
        self.collection = settings.QDRANT_COLLECTION
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            existing = [c.name for c in self.client.get_collections().collections]
            if self.collection not in existing:
                self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config=qm.VectorParams(
                        size=settings.EMBEDDING_DIM,
                        distance=qm.Distance.COSINE,
                        on_disk=True,
                    ),
                    quantization_config=qm.ScalarQuantization(
                        scalar=qm.ScalarQuantizationConfig(
                            type=qm.ScalarType.INT8,
                            quantile=0.99,
                            always_ram=False,
                        )
                    ),
                    on_disk_payload=True,
                )
                logger.info(
                    "Created Qdrant collection '%s' (on_disk=True, quantization=INT8)",
                    self.collection,
                )
        except Exception as exc:
            logger.warning("Could not connect or configure Qdrant collection on init: %s", exc)

    @staticmethod
    def _str_to_uint64(s: str) -> int:
        """Qdrant requires integer or UUID point IDs. Hash tile_id string to uint64."""
        return int(hashlib.md5(s.encode()).hexdigest()[:16], 16)

    def upsert_tile(self, tile_id: str, vector, payload: dict):
        # Store the original string id in payload for retrieval
        payload = dict(payload)
        payload["tile_id"] = tile_id
        self.client.upsert(
            collection_name=self.collection,
            points=[qm.PointStruct(
                id=self._str_to_uint64(tile_id),
                vector=vector.tolist(),
                payload=payload,
            )],
        )

    def delete_tile(self, tile_id: str):
        self.client.delete(
            collection_name=self.collection,
            points_selector=qm.PointIdsList(points=[self._str_to_uint64(tile_id)]),
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
                rng["gte"] = str(date_from)[:19]
            if date_to:
                rng["lte"] = str(date_to)[:19]
            must.append(qm.FieldCondition(key="acquisition_date", range=qm.DatetimeRange(**rng)))
        if aoi_bbox:
            min_lon, min_lat, max_lon, max_lat = aoi_bbox
            must.append(qm.FieldCondition(key="lon", range=qm.Range(gte=min_lon, lte=max_lon)))
            must.append(qm.FieldCondition(key="lat", range=qm.Range(gte=min_lat, lte=max_lat)))

        query_filter = qm.Filter(must=must) if must else None

        # qdrant-client >= 1.10: use query_points() instead of the removed search()
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector.tolist(),
            query_filter=query_filter,
            limit=top_k,
            score_threshold=min_similarity if min_similarity > 0 else None,
            with_payload=True,
        )
        return response.points


vector_store = VectorStore()
