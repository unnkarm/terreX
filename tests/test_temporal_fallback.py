from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import services.dense_change_detection as dense


def _candidates(count):
    return [{"acquisition_date": datetime(2026, 1, 1 + index * 5)} for index in range(count)]


def test_two_to_four_observations_use_bitemporal(monkeypatch):
    monkeypatch.setattr(dense, "find_candidate_tiles", lambda *args, **kwargs: _candidates(2))
    monkeypatch.setattr(dense, "run_change_detection", lambda *args, **kwargs: {"status": "ok", "method": "spectral-diff"})

    result = dense.run_dense_change_detection(
        lon=88.44, lat=22.58, date_from="2026-01-01", date_to="2026-01-10"
    )

    assert result["status"] == "ok"
    assert result["is_fallback"] is True
    assert result["analysis_mode"] == "bi-temporal"
    assert result["available_dates"] == ["2026-01-01", "2026-01-06"]


def test_sparse_window_returns_nearest_dates(monkeypatch):
    monkeypatch.setattr(dense, "find_candidate_tiles", lambda *args, **kwargs: _candidates(1))
    monkeypatch.setattr(dense, "list_available_acquisitions", lambda *args, **kwargs: [
        {"date_formatted": "2026-01-01"}, {"date_formatted": "2026-01-06"}
    ])

    result = dense.run_dense_change_detection(
        lon=88.44, lat=22.58, date_from="2026-01-02", date_to="2026-01-04"
    )

    assert result["status"] == "insufficient_data"
    assert result["available_dates"] == ["2026-01-01", "2026-01-06"]
    assert "Showing nearest available acquisitions" in result["message"]
