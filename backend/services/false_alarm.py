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
from typing import List, Optional, Dict, Any

import numpy as np

from config import settings


@dataclass
class ObservationQuality:
    cloud_fraction: float
    valid_pixel_fraction: float
    sharpness: float
    quality_score: float


@dataclass
class ConfoundFactor:
    factor: str          # "cloud_contamination" | "poor_registration" | "insufficient_corroboration" | "radiometric_shift" | "missing_pixels"
    severity: str        # "high" | "medium" | "low"
    penalty_factor: float
    explanation: str


@dataclass
class SuppressionResult:
    change_score: float
    quality_score: float
    confidence: float
    reasons: List[str] = field(default_factory=list)
    confounds: List[ConfoundFactor] = field(default_factory=list)
    is_high_certainty: bool = True
    confidence_breakdown: Dict[str, Any] = field(default_factory=dict)


def evaluate(
    raw_change_score: float,
    before_q: ObservationQuality,
    after_q: ObservationQuality,
    registration_correlation: float,
    radiometric_diff: float,
    temporal_series: Optional[List[float]] = None,  # raw change scores at other dates, if any
) -> SuppressionResult:
    reasons: List[str] = []
    confounds: List[ConfoundFactor] = []
    score = raw_change_score
    combined_quality = min(before_q.quality_score, after_q.quality_score)

    # 1. Cloud contamination
    if before_q.cloud_fraction > settings.CLOUD_FRACTION_MAX or after_q.cloud_fraction > settings.CLOUD_FRACTION_MAX:
        penalty = 0.25
        score *= penalty
        msg = (
            f"High cloud/haze fraction detected (before={before_q.cloud_fraction:.2f}, "
            f"after={after_q.cloud_fraction:.2f}) - change signal heavily discounted."
        )
        reasons.append(msg)
        confounds.append(ConfoundFactor(
            factor="cloud_contamination",
            severity="high" if max(before_q.cloud_fraction, after_q.cloud_fraction) > 0.5 else "medium",
            penalty_factor=penalty,
            explanation=msg,
        ))

    # 2. Missing / invalid pixels
    if before_q.valid_pixel_fraction < 0.7 or after_q.valid_pixel_fraction < 0.7:
        penalty = 0.5
        score *= penalty
        msg = "Significant missing/invalid pixel coverage in one or both observations."
        reasons.append(msg)
        confounds.append(ConfoundFactor(
            factor="missing_pixels",
            severity="medium",
            penalty_factor=penalty,
            explanation=msg,
        ))

    # 3. Registration / alignment
    if registration_correlation < 0.5:
        penalty = 0.3
        score *= penalty
        msg = (
            f"Poor spatial registration between before/after imagery "
            f"(correlation={registration_correlation:.2f}) - likely misalignment artefact."
        )
        reasons.append(msg)
        confounds.append(ConfoundFactor(
            factor="poor_registration",
            severity="high",
            penalty_factor=penalty,
            explanation=msg,
        ))
    elif registration_correlation < 0.70:
        penalty = 0.75
        score *= penalty
        msg = f"Moderate spatial registration uncertainty (correlation={registration_correlation:.2f})."
        reasons.append(msg)
        confounds.append(ConfoundFactor(
            factor="poor_registration",
            severity="low",
            penalty_factor=penalty,
            explanation=msg,
        ))

    # 4. Extreme radiometric differences (e.g. different lighting/season, sensor gain)
    if radiometric_diff > 0.6:
        penalty = 0.6
        score *= penalty
        msg = (
            f"Large whole-scene radiometric shift ({radiometric_diff:.2f}) suggests "
            "illumination/seasonal/sensor differences rather than ground change."
        )
        reasons.append(msg)
        confounds.append(ConfoundFactor(
            factor="radiometric_shift",
            severity="medium",
            penalty_factor=penalty,
            explanation=msg,
        ))

    # 5. Temporal consistency / corroboration
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
            penalty = 0.7
            score *= penalty
            msg = "No corroborating change in other available observations in the time window."
            reasons.append(msg)
            confounds.append(ConfoundFactor(
                factor="insufficient_corroboration",
                severity="medium",
                penalty_factor=penalty,
                explanation=msg,
            ))
    elif not temporal_series or len(temporal_series) <= 1:
        confounds.append(ConfoundFactor(
            factor="single_observation_pair",
            severity="low",
            penalty_factor=1.0,
            explanation="Single before/after observation pair evaluated (stack history limited).",
        ))

    score = float(np.clip(score, 0.0, 1.0))
    confidence = float(np.clip(0.6 * score + 0.4 * combined_quality, 0.0, 1.0))
    is_high_certainty = confidence >= 0.75 and len([c for c in confounds if c.severity in ("high", "medium")]) == 0

    if not reasons:
        reasons.append("No quality issues detected; change signal taken at face value.")

    confidence_breakdown = {
        "raw_change_score": round(raw_change_score, 4),
        "post_suppression_change_score": round(score, 4),
        "combined_optical_quality": round(combined_quality, 4),
        "final_confidence": round(confidence, 4),
        "is_high_certainty": is_high_certainty,
        "confounds": [
            {
                "factor": c.factor,
                "severity": c.severity,
                "penalty_factor": c.penalty_factor,
                "explanation": c.explanation,
            }
            for c in confounds
        ],
    }

    return SuppressionResult(
        change_score=round(score, 4),
        quality_score=round(combined_quality, 4),
        confidence=round(confidence, 4),
        reasons=reasons,
        confounds=confounds,
        is_high_certainty=is_high_certainty,
        confidence_breakdown=confidence_breakdown,
    )
