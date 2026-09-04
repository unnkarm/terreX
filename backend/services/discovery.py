"""Unsupervised discovery over the vectors already indexed in Qdrant."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sqlalchemy import select

from db.database import get_session
from db.models import Tile
from services.ranking import compute_final_score
from services.vector_store import vector_store


class DiscoveryError(RuntimeError):
    pass


class ReferenceTileNotFound(DiscoveryError):
    pass


def _normalise_vectors(vectors: list[list[float]]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or not np.isfinite(matrix).all():
        raise DiscoveryError("Stored vectors are empty or invalid")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms <= 1e-8):
        raise DiscoveryError("Stored vectors contain a zero-length embedding")
    return matrix / norms


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.clip(np.dot(left, right), -1.0, 1.0))


def _iso_date(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _site_result(tile: Tile, similarity: float, is_placeholder: bool) -> dict:
    final_score, breakdown = compute_final_score(
        semantic_score=similarity,
        quality_score=tile.quality_score or 0.0,
        is_placeholder=is_placeholder,
    )
    breakdown["discovery_ranking"] = "cosine similarity to cluster reference"
    return {
        "tile_id": tile.tile_id,
        "scene_id": tile.scene_id,
        "lon": tile.lon,
        "lat": tile.lat,
        "similarity_score": float(similarity),
        "raw_similarity": float(similarity),
        "final_score": final_score,
        "score_breakdown": breakdown,
        "acquisition_date": _iso_date(tile.acquisition_date),
        "sensor": tile.sensor,
        "quality_score": tile.quality_score,
        "cloud_fraction": tile.cloud_fraction,
        "thumbnail_path": tile.thumbnail_path,
        "embedding_model": tile.embedding_model,
        "embedding_is_placeholder": bool(tile.embedding_is_placeholder),
        "classification_label": "Unclassified",
    }


def _characteristics(sites: list[Tile]) -> list[str]:
    characteristics = []
    sensors = sorted({site.sensor for site in sites if site.sensor})
    if sensors:
        characteristics.append(f"Sensor: {', '.join(sensors)}")
    dates = [site.acquisition_date for site in sites if site.acquisition_date]
    if dates:
        characteristics.append(f"Acquisition span: {min(dates).date().isoformat()} to {max(dates).date().isoformat()}")
    qualities = [site.quality_score for site in sites if site.quality_score is not None]
    if qualities:
        characteristics.append(f"Mean quality score: {np.mean(qualities):.3f}")
    clouds = [site.cloud_fraction for site in sites if site.cloud_fraction is not None]
    if clouds:
        characteristics.append(f"Mean cloud fraction: {np.mean(clouds):.3f}")
    return characteristics or ["No additional metadata available"]


def discover(tile_id: Optional[str] = None, max_clusters: int = 4, top_k: int = 20) -> dict:
    if max_clusters < 1 or top_k < 1:
        raise DiscoveryError("max_clusters and top_k must be positive")

    points = vector_store.scroll_vectors()
    if not points:
        raise DiscoveryError("No vectors are indexed")

    point_by_tile = {point["tile_id"]: point for point in points if point.get("tile_id")}
    if tile_id and tile_id not in point_by_tile:
        raise ReferenceTileNotFound(f"Tile '{tile_id}' is not indexed")

    tile_ids = list(point_by_tile)
    with get_session() as session:
        session.expire_on_commit = False
        tiles = {
            tile.tile_id: tile
            for tile in session.execute(select(Tile).where(Tile.tile_id.in_(tile_ids))).scalars()
        }

    usable = [point for point in points if point.get("tile_id") in tiles]
    if not usable:
        raise DiscoveryError("Indexed vectors have no matching tile metadata")

    vectors = _normalise_vectors([point["vector"] for point in usable])
    if len(usable) == 1:
        labels = np.zeros(1, dtype=int)
    else:
        cluster_count = min(max_clusters, max(2, int(np.sqrt(len(usable)))))
        cluster_count = min(cluster_count, len(usable))
        labels = AgglomerativeClustering(
            n_clusters=cluster_count,
            metric="cosine",
            linkage="average",
        ).fit_predict(vectors)

    reference_index = None
    if tile_id:
        reference_index = next(i for i, point in enumerate(usable) if point["tile_id"] == tile_id)

    placeholder_flags = [bool(tiles[point["tile_id"]].embedding_is_placeholder) for point in usable]
    models = [tiles[point["tile_id"]].embedding_model for point in usable if tiles[point["tile_id"]].embedding_model]
    clusters = []
    for label in sorted(set(labels.tolist())):
        indices = np.flatnonzero(labels == label).tolist()
        cluster_vectors = vectors[indices]
        centroid_vector = np.mean(cluster_vectors, axis=0)
        centroid_vector /= np.linalg.norm(centroid_vector) or 1.0
        cohesion = np.clip(cluster_vectors @ centroid_vector, 0.0, 1.0)
        sites = [tiles[usable[index]["tile_id"]] for index in indices]
        ranked_indices = sorted(indices, key=lambda index: _cosine(vectors[index], centroid_vector), reverse=True)
        if reference_index is not None and reference_index in indices:
            ranked_indices = sorted(indices, key=lambda index: _cosine(vectors[index], vectors[reference_index]), reverse=True)
        ranked_indices = ranked_indices[:top_k]
        site_results = [
            _site_result(
                tiles[usable[index]["tile_id"]],
                _cosine(vectors[index], vectors[reference_index] if reference_index is not None else centroid_vector),
                placeholder_flags[index],
            )
            for index in ranked_indices
        ]
        lon_values = [site.lon for site in sites]
        lat_values = [site.lat for site in sites]
        cluster = {
            "id": f"embedding-cluster-{label + 1}",
            "name": "Embedding cluster",
            "count": len(indices),
            "centroid": [float(np.mean(lon_values)), float(np.mean(lat_values))],
            "confidence": float(np.mean(cohesion)),
            "dominantType": "Unclassified",
            "characteristics": _characteristics(sites),
            "sites": site_results,
        }
        if reference_index is not None and reference_index in indices:
            cluster["name"] = "Reference embedding cluster"
            cluster["characteristics"].insert(0, "Contains the requested reference tile")
        clusters.append(cluster)

    if reference_index is not None:
        reference_label = labels[reference_index]
        clusters.sort(key=lambda cluster: cluster["id"] != f"embedding-cluster-{reference_label + 1}")

    return {
        "embedding_model": models[0] if len(set(models)) == 1 and models else ("mixed" if models else None),
        "embedding_is_placeholder": any(placeholder_flags),
        "total_candidates": len(usable),
        "clusters": clusters,
    }
