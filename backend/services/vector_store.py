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


def _sensor_aliases(sensor: str) -> list[str]:
    normalized = sensor.lower().replace("-", "").replace("_", "").replace(" ", "")
    aliases = {sensor}
    if "sentinel2" in normalized:
        aliases.update({"Sentinel-2", "Sentinel-2 MSI", "Sentinel2", "sentinel-2", "sentinel2"})
    elif "sentinel1" in normalized:
        aliases.update({"Sentinel-1", "Sentinel-1 SAR", "Sentinel1", "sentinel-1", "sentinel1"})
    elif "landsat8" in normalized:
        aliases.update({"Landsat-8", "Landsat-8 OLI", "Landsat8", "landsat-8", "landsat8"})
    return sorted(aliases)


class VectorStore:
    def __init__(self):
        self.collection = settings.QDRANT_COLLECTION
        try:
            self.client = QdrantClient(url=settings.QDRANT_URL)
            self._ensure_collection()
        except Exception as exc:
            logger.warning("Could not connect to Qdrant at %s, using local in-memory/DB fallback: %s", settings.QDRANT_URL, exc)

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

    def _str_to_uint64(self, s: str) -> int:
        """Convert arbitrary string (UUID, scene_id) into uint64 ID for Qdrant."""
        return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:15], 16)

    def upsert_tile(
        self,
        tile_id: str,
        vector: list[float],
        sensor: str,
        acquisition_date: Optional[str] = None,
        lon: Optional[float] = None,
        lat: Optional[float] = None,
        extra_payload: Optional[dict] = None,
    ):
        payload = {
            "tile_id": tile_id,
            "sensor": sensor,
            "acquisition_date": acquisition_date,
            "lon": lon,
            "lat": lat,
        }
        if extra_payload:
            payload.update(extra_payload)

        try:
            self.client.upsert(
                collection_name=self.collection,
                points=[
                    qm.PointStruct(
                        id=self._str_to_uint64(tile_id),
                        vector=vector,
                        payload=payload,
                    )
                ],
            )
        except Exception as exc:
            logger.warning("Qdrant upsert failed for tile %s: %s", tile_id, exc)

    def delete_tile(self, tile_id: str):
        try:
            self.client.delete(
                collection_name=self.collection,
                points_selector=qm.PointIdsList(points=[self._str_to_uint64(tile_id)]),
            )
        except Exception as exc:
            logger.warning("Qdrant delete failed for tile %s: %s", tile_id, exc)

    def count(self) -> int:
        """Return the number of indexed vectors, falling back to DB tiles when Qdrant is offline."""
        try:
            cnt = int(self.client.count(collection_name=self.collection, exact=True).count)
            if cnt > 0:
                return cnt
        except Exception as exc:
            logger.debug("Could not count vectors in '%s': %s", self.collection, exc)
        
        # Fallback to counting database tiles with embeddings or valid geometries
        try:
            from db.database import get_session
            from db.models import Tile
            from sqlalchemy import select, func
            with get_session() as session:
                return int(session.scalar(select(func.count(Tile.tile_id))) or 0)
        except Exception:
            return 0

    def scroll_vectors(self, batch_size: int = 256) -> list[dict]:
        """Return every stored point, including its vector and payload."""
        points = []
        offset = None
        try:
            while True:
                batch, offset = self.client.scroll(
                    collection_name=self.collection,
                    offset=offset,
                    limit=batch_size,
                    with_payload=True,
                    with_vectors=True,
                )
                for point in batch:
                    payload = point.payload or {}
                    points.append({
                        "tile_id": payload.get("tile_id"),
                        "point_id": point.id,
                        "vector": point.vector,
                        "payload": payload,
                    })
                if offset is None:
                    break
            return points
        except Exception as exc:
            logger.warning("Qdrant scroll_vectors failed (%s), querying DB directly...", exc)
            from db.database import get_session
            from db.models import Tile
            from sqlalchemy import select
            from sqlalchemy.orm import defer

            with get_session() as session:
                tiles = session.execute(select(Tile).options(defer(Tile.geometry))).scalars().all()
                for t in tiles:
                    if t.embedding is not None:
                        points.append({
                            "tile_id": t.tile_id,
                            "point_id": t.tile_id,
                            "vector": t.embedding,
                            "payload": {"tile_id": t.tile_id, "sensor": t.sensor, "lon": t.lon, "lat": t.lat},
                        })
            return points

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
            aliases = _sensor_aliases(sensor)
            match = qm.MatchAny(any=aliases) if len(aliases) > 1 else qm.MatchValue(value=sensor)
            must.append(qm.FieldCondition(key="sensor", match=match))
        if date_from or date_to:
            rng = {}
            if date_from:
                df = str(date_from)[:19]
                if len(df) == 10:
                    df += "T00:00:00Z"
                elif not df.endswith("Z") and not "+" in df:
                    df += "Z"
                rng["gte"] = df
            if date_to:
                dt = str(date_to)[:19]
                if len(dt) == 10:
                    dt += "T23:59:59Z"
                elif not dt.endswith("Z") and not "+" in dt:
                    dt += "Z"
                rng["lte"] = dt
            must.append(qm.FieldCondition(key="acquisition_date", range=qm.DatetimeRange(**rng)))
        if aoi_bbox:
            min_lon, min_lat, max_lon, max_lat = aoi_bbox
            must.append(qm.FieldCondition(key="lon", range=qm.Range(gte=min_lon, lte=max_lon)))
            must.append(qm.FieldCondition(key="lat", range=qm.Range(gte=min_lat, lte=max_lat)))

        query_filter = qm.Filter(must=must) if must else None

        try:
            response = self.client.search(
                collection_name=self.collection,
                query_vector=vector.tolist() if hasattr(vector, "tolist") else list(vector),
                query_filter=query_filter,
                limit=top_k,
                score_threshold=min_similarity if min_similarity > 0 else None,
                with_payload=True,
            )
            return response
        except Exception as exc:
            logger.warning("Qdrant search failed (%s), falling back to database cosine similarity...", exc)
            return self._db_fallback_search(vector, top_k, sensor, min_similarity, aoi_bbox, date_from, date_to)

    def _db_fallback_search(
        self,
        vector,
        top_k: int,
        sensor: Optional[str],
        min_similarity: float,
        aoi_bbox: Optional[tuple] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ):
        import numpy as np
        from db.database import get_session
        from db.models import Tile
        from sqlalchemy import select
        from sqlalchemy.orm import defer

        class FallbackHit:
            def __init__(self, tile_id: str, score: float):
                self.id = tile_id
                self.score = score
                self.payload = {"tile_id": tile_id}

        norm_vec = np.array(vector, dtype=np.float32)
        norm_val = np.linalg.norm(norm_vec)
        if norm_val > 0:
            norm_vec /= norm_val

        hits = []
        with get_session() as session:
            query = select(Tile).options(defer(Tile.geometry))
            if sensor:
                query = query.where(Tile.sensor.in_(_sensor_aliases(sensor)))
            if aoi_bbox:
                min_lon, min_lat, max_lon, max_lat = aoi_bbox
                query = query.where(
                    Tile.lon >= min_lon,
                    Tile.lon <= max_lon,
                    Tile.lat >= min_lat,
                    Tile.lat <= max_lat,
                )
            if date_from:
                query = query.where(Tile.acquisition_date >= date_from[:10])
            if date_to:
                query = query.where(Tile.acquisition_date <= date_to[:10] + " 23:59:59")

            tiles = session.execute(query).scalars().all()

            for t in tiles:
                if t.embedding is None:
                    continue
                tile_emb = np.array(t.embedding, dtype=np.float32)
                tnorm = np.linalg.norm(tile_emb)
                if tnorm > 0:
                    tile_emb /= tnorm
                sim = float(np.dot(norm_vec, tile_emb))
                if min_similarity <= 0 or sim >= min_similarity:
                    hits.append(FallbackHit(t.tile_id, sim))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]


vector_store = VectorStore()
