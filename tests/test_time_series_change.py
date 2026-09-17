from datetime import datetime, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.time_series_change import PassSignal, detect_change_point


def _passes(scores, invalid=()):
    start = datetime(2026, 1, 1)
    return [
        PassSignal(
            timestamp=start + timedelta(days=index * 5),
            score=score,
            valid=index not in invalid,
            tile_id=f"tile-{index}",
            modality="sar" if index % 2 else "optical",
        )
        for index, score in enumerate(scores)
    ]


def test_confirms_first_of_two_persistent_valid_passes():
    result = detect_change_point(_passes([0.02, 0.03, 0.04, 0.72, 0.81]), baseline_n=3, persistence_k=2)
    assert result.status == "confirmed"
    assert result.onset_index == 3
    assert result.confirmation_index == 4
    assert result.temporal_uncertainty_days == 5.0
    assert result.confirmation_lag_days == 5.0


def test_suppresses_single_pass_that_reverts():
    result = detect_change_point(_passes([0.02, 0.03, 0.04, 0.8, 0.1, 0.2]), baseline_n=3, persistence_k=2)
    assert result.status == "transient_only"
    assert result.transient_indices == [3]
    assert any(item["event"] == "transient_suppressed" for item in result.log)


def test_invalid_cloudy_pass_does_not_break_persistence():
    result = detect_change_point(
        _passes([0.02, 0.03, 0.04, 0.75, 0.01, 0.82], invalid={4}),
        baseline_n=3,
        persistence_k=2,
    )
    assert result.status == "confirmed"
    assert result.onset_index == 3
    assert result.confirmation_index == 5


def test_requires_enough_valid_baseline_passes():
    result = detect_change_point(_passes([0.1, 0.2, 0.8], invalid={1}), baseline_n=3, persistence_k=2)
    assert result.status == "insufficient_data"
