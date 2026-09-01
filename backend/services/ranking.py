"""
Feature 6 — Hybrid ranking.

Combines semantic similarity + geographic relevance + metadata match +
image quality + change confidence into one configurable score. Weights
live in config.py (env-overridable) so the function stays simple and the
knobs stay visible for the demo.
"""
from __future__ import annotations

from typing import Optional

from config import settings


def compute_final_score(
    semantic_score: float,
    quality_score: float,
    geo_relevance: float = 1.0,
    metadata_match: float = 1.0,
    change_confidence: Optional[float] = None,
) -> tuple:
    """
    All inputs expected in [0, 1]. Returns (final_score, breakdown_dict).
    If change_confidence is None (no change context for this query), its
    weight is redistributed proportionally across the other terms so the
    score stays on a comparable 0..1 scale.
    """
    w_sem, w_geo, w_meta, w_qual, w_change = (
        settings.W_SEMANTIC, settings.W_GEO, settings.W_METADATA,
        settings.W_QUALITY, settings.W_CHANGE,
    )

    if change_confidence is None:
        remaining = w_sem + w_geo + w_meta + w_qual
        scale = 1.0 / remaining if remaining > 0 else 0.0
        w_sem, w_geo, w_meta, w_qual = (w * scale for w in (w_sem, w_geo, w_meta, w_qual))
        w_change = 0.0
        change_confidence = 0.0

    final = (
        w_sem * semantic_score
        + w_geo * geo_relevance
        + w_meta * metadata_match
        + w_qual * quality_score
        + w_change * change_confidence
    )
    breakdown = {
        "semantic": round(semantic_score, 4),
        "geo_relevance": round(geo_relevance, 4),
        "metadata_match": round(metadata_match, 4),
        "quality": round(quality_score, 4),
        "change_confidence": round(change_confidence, 4),
        "weights": {
            "semantic": round(w_sem, 3), "geo": round(w_geo, 3),
            "metadata": round(w_meta, 3), "quality": round(w_qual, 3),
            "change": round(w_change, 3),
        },
    }
    return round(final, 4), breakdown
