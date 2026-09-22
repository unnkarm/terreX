"""
Feature 6 — Hybrid ranking.

Combines semantic similarity + geographic relevance + metadata match +
image quality + change confidence into one calibrated score.
"""
from __future__ import annotations

import re
from typing import Optional
import numpy as np

from config import settings


TEMPORAL_CHANGE_KEYWORDS = frozenset({
    "new", "recent", "constructed", "construction", "cleared", "clearance",
    "development", "developed", "expanded", "expansion", "built", "changed", "change",
})


def detect_temporal_query_intent(query: Optional[str]) -> tuple[bool, list[str]]:
    """Detect explicit physical-change intent without substring false positives."""
    tokens = set(re.findall(r"[a-z0-9]+", (query or "").lower()))
    matches = sorted(tokens.intersection(TEMPORAL_CHANGE_KEYWORDS))
    return bool(matches), matches


def calibrate_similarity(raw_score: float, is_placeholder: bool = False) -> float:
    """
    Calibrates raw RemoteCLIP cosine similarity into a standardized 0..1 scale.
    For RemoteCLIP embeddings, random/unrelated cosine is ~0.14-0.16.
    A score of 0.21 indicates moderate relevance (50%), 0.25 is strong (75%), and 0.28+ is very high (90%+).
    """
    if is_placeholder:
        return float(np.clip(raw_score, 0.0, 1.0))
    # RemoteCLIP calibration curve
    calibrated = (raw_score - 0.15) / 0.14
    return float(np.clip(calibrated, 0.0, 1.0))


def compute_final_score(
    semantic_score: float,
    quality_score: float,
    geo_relevance: float = 1.0,
    metadata_match: float = 1.0,
    change_confidence: Optional[float] = None,
    is_placeholder: bool = False,
    temporal_query: bool = False,
) -> tuple:
    """
    Calculates calibrated final ranking score.
    Semantic similarity acts as the primary gatekeeper so irrelevant tiles
    do not rank high purely due to image quality or metadata.
    """
    calibrated_sem = calibrate_similarity(semantic_score, is_placeholder)

    # Relevance gate: if semantic similarity is low, suppress composite score
    if calibrated_sem < 0.15:
        relevance_gate = calibrated_sem / 0.15
    else:
        relevance_gate = 1.0

    change_value = float(np.clip(change_confidence or 0.0, 0.0, 1.0))
    if temporal_query:
        # Temporal queries keep semantic retrieval as the candidate generator,
        # but physical delta becomes the primary reranking evidence.
        weights = {"semantic": 0.45, "change": 0.35, "quality": 0.10, "geo": 0.10, "metadata": 0.0}
    else:
        weights = {
            "semantic": float(settings.W_SEMANTIC),
            "change": float(settings.W_CHANGE),
            "quality": float(settings.W_QUALITY),
            "geo": float(settings.W_GEO),
            "metadata": float(settings.W_METADATA),
        }

    base_score = (
        weights["semantic"] * calibrated_sem
        + weights["change"] * change_value
        + weights["quality"] * float(quality_score)
        + weights["geo"] * float(geo_relevance)
        + weights["metadata"] * float(metadata_match)
    )

    # When a geographic target was extracted, apply spatial decay gating
    # so out-of-district tiles are suppressed
    geo_gate = (float(geo_relevance) ** 1.5) if geo_relevance < 0.999 else 1.0
    final = float(np.clip(base_score * relevance_gate * geo_gate, 0.0, 1.0))

    breakdown = {
        "raw_similarity": round(semantic_score, 4),
        "semantic": round(calibrated_sem, 4),
        "geo_relevance": round(geo_relevance, 4),
        "metadata_match": round(metadata_match, 4),
        "quality": round(quality_score, 4),
        "change_confidence": round(change_value, 4),
        "ranking_mode": "change-aware" if temporal_query else "hybrid",
        "weights": weights,
    }
    return round(final, 4), breakdown
