"""Pure temporal change-point detection for dense EO observation stacks.

The image/scientific pipeline is responsible for producing one normalized change
signal per usable pass.  This module only handles the temporal contract: a stable
baseline window, consecutive-pass persistence, transient rejection, and bounded
onset timing.  Keeping it pure makes the most consequential decision logic easy
to unit test without databases or model weights.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class PassSignal:
    timestamp: datetime
    score: float
    valid: bool = True
    tile_id: str = ""
    modality: str = "optical"
    quality_score: float = 1.0


@dataclass
class ChangePointResult:
    status: str
    baseline_indices: list[int] = field(default_factory=list)
    onset_index: Optional[int] = None
    confirmation_index: Optional[int] = None
    earliest_supported: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    last_clear_at: Optional[datetime] = None
    temporal_uncertainty_days: Optional[float] = None
    confirmation_lag_days: Optional[float] = None
    transient_indices: list[int] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_confirmed(self) -> bool:
        return self.status == "confirmed"


def detect_change_point(
    passes: Iterable[PassSignal],
    *,
    baseline_n: int = 3,
    persistence_k: int = 2,
    threshold: float = 0.5,
) -> ChangePointResult:
    """Confirm the first change that persists for ``persistence_k`` valid passes.

    Invalid observations never count toward the baseline or confirmation run and
    do not break a candidate run: they represent a gap, not evidence of recovery.
    A valid below-threshold observation does break the run and records its earlier
    members as transient confounders.
    """
    if baseline_n < 1:
        raise ValueError("baseline_n must be at least 1")
    if persistence_k < 2:
        raise ValueError("persistence_k must be at least 2")
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be in (0, 1]")

    ordered = sorted(list(passes), key=lambda item: item.timestamp)
    baseline_indices: list[int] = []
    for index, item in enumerate(ordered):
        if item.valid:
            baseline_indices.append(index)
            if len(baseline_indices) == baseline_n:
                break

    result = ChangePointResult(status="insufficient_data", baseline_indices=baseline_indices)
    if len(baseline_indices) < baseline_n:
        result.log.append({
            "event": "insufficient_baseline",
            "required": baseline_n,
            "available": len(baseline_indices),
        })
        return result

    baseline_end = baseline_indices[-1]
    result.log.append({
        "event": "baseline_established",
        "pass_indices": baseline_indices,
        "start": ordered[baseline_indices[0]].timestamp.isoformat(),
        "end": ordered[baseline_end].timestamp.isoformat(),
    })

    run: list[int] = []
    last_clear_index = baseline_end
    post_baseline_valid = 0

    for index in range(baseline_end + 1, len(ordered)):
        item = ordered[index]
        if not item.valid:
            result.log.append({
                "event": "invalid_pass_skipped",
                "index": index,
                "timestamp": item.timestamp.isoformat(),
                "tile_id": item.tile_id,
                "modality": item.modality,
                "quality_score": round(float(item.quality_score), 4),
            })
            continue

        post_baseline_valid += 1
        above = float(item.score) >= threshold
        result.log.append({
            "event": "threshold_evaluation",
            "index": index,
            "timestamp": item.timestamp.isoformat(),
            "tile_id": item.tile_id,
            "modality": item.modality,
            "score": round(float(item.score), 4),
            "threshold": threshold,
            "above_threshold": above,
        })

        if above:
            run.append(index)
            if len(run) >= persistence_k:
                onset_index = run[0]
                confirmation_index = run[persistence_k - 1]
                onset = ordered[onset_index].timestamp
                confirmation = ordered[confirmation_index].timestamp
                last_clear = ordered[last_clear_index].timestamp
                result.status = "confirmed"
                result.onset_index = onset_index
                result.confirmation_index = confirmation_index
                result.earliest_supported = onset
                result.confirmed_at = confirmation
                result.last_clear_at = last_clear
                result.temporal_uncertainty_days = round(
                    max(0.0, (onset - last_clear).total_seconds() / 86400.0), 3
                )
                result.confirmation_lag_days = round(
                    max(0.0, (confirmation - onset).total_seconds() / 86400.0), 3
                )
                result.log.append({
                    "event": "change_confirmed",
                    "onset_index": onset_index,
                    "confirmation_index": confirmation_index,
                    "earliest_supported": onset.isoformat(),
                    "confirmed_at": confirmation.isoformat(),
                    "consecutive_valid_passes": persistence_k,
                })
                return result
        else:
            if run:
                result.transient_indices.extend(run)
                result.log.append({
                    "event": "transient_suppressed",
                    "pass_indices": list(run),
                    "reverted_at": item.timestamp.isoformat(),
                    "reason": "The anomaly did not persist into the next valid observation.",
                })
                run = []
            last_clear_index = index

    if run:
        result.transient_indices.extend(run)
        result.log.append({
            "event": "unconfirmed_tail",
            "pass_indices": list(run),
            "reason": "The time window ended before the persistence requirement was met.",
        })

    if post_baseline_valid == 0:
        result.status = "insufficient_data"
    elif result.transient_indices:
        result.status = "transient_only"
    else:
        result.status = "no_change"
    return result
