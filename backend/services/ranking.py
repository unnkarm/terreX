"""
Feature 6 — Hybrid ranking.

Combines semantic similarity + geographic relevance + metadata match +
image quality + change confidence into one calibrated score.
"""
from __future__ import annotations

from typing import Optional
import numpy as np


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

    w_sem = 0.65
    w_qual = 0.15
    w_meta = 0.10
    w_geo = 0.10

    base_score = (
        w_sem * calibrated_sem
        + w_qual * float(quality_score)
        + w_meta * float(metadata_match)
        + w_geo * float(geo_relevance)
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
        "change_confidence": round(change_confidence, 4) if change_confidence else 0.0,
    }
    return round(final, 4), breakdown

