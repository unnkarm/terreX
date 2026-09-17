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
    evidence_agreement: Optional[float] = None,     # 0..1 weighted share of evidence layers that fired
    evidence_layers: Optional[List[Dict[str, Any]]] = None,
    clear_fraction: Optional[float] = None,         # usable fraction after cloud/quality masking
    radiometry_normalized: bool = False,            # a gain/offset correction was already applied
    registration_residual_px: Optional[float] = None,  # misalignment measured AFTER warping
    registration_aligned: Optional[bool] = None,       # whether co-registration succeeded
) -> SuppressionResult:
    """
    Score a change detection at scene level.

    The optional arguments carry the multi-evidence pipeline's own diagnostics:
    how many independent evidence layers corroborated the detection, how much
    of the tile survived cloud/quality masking, and whether radiometry was
    already normalized. When they are omitted the function behaves exactly as
    the original single-signal scorer.

    `registration_residual_px` deserves a note. Correlation between two dates
    falls both with misalignment and with genuine ground change, so scoring
    alignment from `registration_correlation` alone penalises exactly the large,
    real changes the detector exists to find. When the caller can supply the
    misalignment measured after warping, that is used instead.
    """
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
    if registration_residual_px is not None:
        # Measured post-warp misalignment: an unambiguous geometry diagnostic
        # that genuine ground change cannot inflate.
        residual = abs(float(registration_residual_px))
        failed = registration_aligned is False
        if residual > 1.5 or failed:
            penalty = 0.3
            score *= penalty
            msg = (
                f"Poor spatial registration: {residual:.2f}px misalignment remains after warping"
                + (" and co-registration did not converge" if failed else "")
                + " - likely misalignment artefact."
            )
            reasons.append(msg)
            confounds.append(ConfoundFactor(
                factor="poor_registration", severity="high", penalty_factor=penalty, explanation=msg,
            ))
        elif residual > 0.5:
            penalty = 0.75
            score *= penalty
            msg = f"Moderate spatial registration uncertainty ({residual:.2f}px residual misalignment)."
            reasons.append(msg)
            confounds.append(ConfoundFactor(
                factor="poor_registration", severity="low", penalty_factor=penalty, explanation=msg,
            ))
    elif registration_correlation < 0.5:
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
        # A pseudo-invariant gain/offset fit has already removed most of a
        # whole-scene illumination difference, so the residual risk is lower.
        penalty = 0.85 if radiometry_normalized else 0.6
        score *= penalty
        msg = (
            f"Large whole-scene radiometric shift ({radiometric_diff:.2f}) suggests "
            "illumination/seasonal/sensor differences rather than ground change."
        )
        if radiometry_normalized:
            msg += " Relative radiometric normalization was applied, so the penalty is reduced."
        reasons.append(msg)
        confounds.append(ConfoundFactor(
            factor="radiometric_shift",
            severity="low" if radiometry_normalized else "medium",
            penalty_factor=penalty,
            explanation=msg,
        ))

    # 5. Temporal consistency / corroboration
    if temporal_series and len(temporal_series) >= 2:
        persistent = sum(1 for v in temporal_series if v > settings.CHANGE_PROB_THRESHOLD)
        if persistent >= max(2, len(temporal_series) - 1):
            boost = min(0.25, 0.06 * persistent)
            score = min(1.0, score + boost * (1.0 - score))
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

    # 6. Cross-evidence corroboration — the multi-evidence pipeline's own vote.
    if evidence_agreement is not None:
        layer_count = len(evidence_layers) if evidence_layers else 0
        if evidence_agreement >= 0.6:
            boost = min(0.15, 0.2 * evidence_agreement)
            score = min(1.0, score + boost * (1.0 - score))
            reasons.append(
                f"Independent evidence layers agree ({evidence_agreement:.0%} weighted agreement"
                + (f" across {layer_count} layers" if layer_count else "")
                + ") — deep, spectral and spatial signals corroborate each other."
            )
        elif evidence_agreement < 0.30:
            penalty = 0.75
            score *= penalty
            msg = (
                f"Only {evidence_agreement:.0%} weighted agreement between independent evidence "
                "layers — the signal rests largely on a single line of evidence."
            )
            reasons.append(msg)
            confounds.append(ConfoundFactor(
                factor="single_evidence_source",
                severity="medium",
                penalty_factor=penalty,
                explanation=msg,
            ))

    # 7. Masked-out coverage — how much of the tile was comparable at all.
    if clear_fraction is not None and clear_fraction < 0.5:
        penalty = 0.6 if clear_fraction < 0.25 else 0.85
        score *= penalty
        msg = (
            f"Only {clear_fraction:.0%} of the tile was usable in both dates after cloud, "
            "shadow and nodata masking."
        )
        reasons.append(msg)
        confounds.append(ConfoundFactor(
            factor="masked_coverage",
            severity="high" if clear_fraction < 0.25 else "medium",
            penalty_factor=penalty,
            explanation=msg,
        ))

    score = float(np.clip(score, 0.0, 1.0))
    if evidence_agreement is None:
        confidence = float(np.clip(0.6 * score + 0.4 * combined_quality, 0.0, 1.0))
    else:
        # Corroboration across independent evidence is worth its own share of
        # the confidence, so a strong score from one layer alone cannot claim
        # the same certainty as a weaker score that every layer agrees on.
        confidence = float(np.clip(
            0.45 * score + 0.35 * combined_quality + 0.20 * float(evidence_agreement), 0.0, 1.0
        ))
    is_high_certainty = confidence >= 0.75 and len([c for c in confounds if c.severity in ("high", "medium")]) == 0

    if not reasons:
        reasons.append("No quality issues detected; change signal taken at face value.")

    confidence_breakdown = {
        "raw_change_score": round(raw_change_score, 4),
        "post_suppression_change_score": round(score, 4),
        "combined_optical_quality": round(combined_quality, 4),
        "evidence_agreement": round(float(evidence_agreement), 4) if evidence_agreement is not None else None,
        "evidence_layers": evidence_layers or [],
        "clear_fraction": round(float(clear_fraction), 4) if clear_fraction is not None else None,
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
