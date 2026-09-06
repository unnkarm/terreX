"""
Feature 5 — False-alarm suppression.

Takes a raw change signal plus quality/registration diagnostics for the
before/after observations (and optionally a short time series) and turns
it into a defensible (change_score, quality_score, confidence, reasons).

This is intentionally rule-based and inspectable rather than a black box —
appropriate for an analyst-facing MVP where every suppression/boost needs
a stated reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from config import settings


@dataclass
class ObservationQuality:
    cloud_fraction: float
    valid_pixel_fraction: float
    sharpness: float
    quality_score: float


@dataclass
class SuppressionResult:
    change_score: float
    quality_score: float
    confidence: float
    reasons: List[str] = field(default_factory=list)


def evaluate(
    raw_change_score: float,
    before_q: ObservationQuality,
    after_q: ObservationQuality,
    registration_correlation: float,
    radiometric_diff: float,
    temporal_series: Optional[List[float]] = None,  # raw change scores at other dates, if any
) -> SuppressionResult:
    reasons: List[str] = []
    score = raw_change_score
    combined_quality = min(before_q.quality_score, after_q.quality_score)

    # 1. Cloud contamination
    if before_q.cloud_fraction > settings.CLOUD_FRACTION_MAX or after_q.cloud_fraction > settings.CLOUD_FRACTION_MAX:
        score *= 0.25
        reasons.append(
            f"High cloud/haze fraction detected (before={before_q.cloud_fraction:.2f}, "
            f"after={after_q.cloud_fraction:.2f}) - change signal heavily discounted."
        )

    # 2. Missing / invalid pixels
    if before_q.valid_pixel_fraction < 0.7 or after_q.valid_pixel_fraction < 0.7:
        score *= 0.5
        reasons.append("Significant missing/invalid pixel coverage in one or both observations.")

    # 3. Overall image quality
    if combined_quality < settings.MIN_QUALITY_SCORE:
        score *= 0.5
        reasons.append(f"Low overall image quality (min quality={combined_quality:.2f}).")

    # 4. Registration / alignment
    if registration_correlation < 0.5:
        score *= 0.3
        reasons.append(
            f"Poor spatial registration between before/after imagery "
            f"(correlation={registration_correlation:.2f}) - likely misalignment artefact."
        )

    # 5. Extreme radiometric differences (e.g. different lighting/season, sensor gain)
    if radiometric_diff > 0.6:
        score *= 0.6
        reasons.append(
            f"Large whole-scene radiometric shift ({radiometric_diff:.2f}) suggests "
            "illumination/seasonal/sensor differences rather than ground change."
        )

    # 6. Temporal consistency boost - real changes tend to persist
    if temporal_series and len(temporal_series) >= 2:
        persistent = sum(1 for v in temporal_series if v > settings.CHANGE_PROB_THRESHOLD)
        if persistent >= max(2, len(temporal_series) - 1):
            boost = min(0.25, 0.06 * persistent)
            score = min(1.0, score + boost)
            reasons.append(
                f"Change persists across {persistent}/{len(temporal_series)} additional "
                "usable observations - confidence boosted."
            )
        elif persistent == 0:
            score *= 0.7
            reasons.append("No corroborating change in other available observations.")

    score = float(np.clip(score, 0.0, 1.0))
    confidence = float(np.clip(0.6 * score + 0.4 * combined_quality, 0.0, 1.0))

    if not reasons:
        reasons.append("No quality issues detected; change signal taken at face value.")

    return SuppressionResult(
        change_score=round(score, 4),
        quality_score=round(combined_quality, 4),
        confidence=round(confidence, 4),
        reasons=reasons,
    )
