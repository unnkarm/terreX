from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.ranking import compute_final_score, detect_temporal_query_intent
from services.search import _spectral_delta_evidence


def test_temporal_intent_uses_whole_words():
    assert detect_temporal_query_intent("new construction near Sector 5") == (True, ["construction", "new"])
    assert detect_temporal_query_intent("renewable energy site")[0] is False


def test_temporal_ranking_promotes_physical_change():
    stable, _ = compute_final_score(0.8, 0.8, change_confidence=0.0, is_placeholder=True, temporal_query=True)
    changed, breakdown = compute_final_score(0.8, 0.8, change_confidence=0.9, is_placeholder=True, temporal_query=True)
    assert changed > stable
    assert breakdown["weights"]["change"] == 0.35
    assert breakdown["weights"]["semantic"] == 0.45
    assert breakdown["ranking_mode"] == "change-aware"


def test_construction_proxy_uses_positive_ndbi_and_vegetation_loss():
    before = SimpleNamespace(
        sensor="MSI", acquisition_date=datetime(2024, 1, 1),
        spectral_indices={"ndbi_mean": -0.10, "ndvi_mean": 0.35, "ndwi_mean": 0.02},
    )
    after = SimpleNamespace(
        sensor="MSI", acquisition_date=datetime(2026, 1, 1),
        spectral_indices={"ndbi_mean": 0.08, "ndvi_mean": 0.08, "ndwi_mean": -0.02},
    )
    evidence = _spectral_delta_evidence([before, after], ["construction", "new"])
    assert evidence["score"] >= 0.75
    assert evidence["deltas"]["d_ndbi"] > 0
    assert evidence["deltas"]["d_ndvi"] < 0
