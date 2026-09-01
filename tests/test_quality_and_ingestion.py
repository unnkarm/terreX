"""
Unit tests for quality diagnostics, false-alarm suppression, and ingestion utilities.
"""
import sys
from pathlib import Path

# Add backend to path for tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import numpy as np
import pytest

from services.quality import (
    cloud_fraction_estimate, valid_pixel_fraction, sharpness_score,
    overall_quality_score, registration_offset_estimate,
)
from services.false_alarm import evaluate, ObservationQuality
from services.ingestion import _compute_tile_bounds_wgs84, _resolve_band_map


def test_cloud_fraction_clear_sky():
    # Green terrain: moderate green, low blue/red, low brightness
    rgb = np.zeros((100, 100, 3), dtype=np.float32)
    rgb[..., 0] = 0.25  # R
    rgb[..., 1] = 0.55  # G
    rgb[..., 2] = 0.20  # B
    frac = cloud_fraction_estimate(rgb)
    assert frac == 0.0


def test_cloud_fraction_cloudy_sky():
    # Bright white haze/cloud: high brightness (> 0.85) and near-zero saturation
    rgb = np.full((100, 100, 3), 0.92, dtype=np.float32)
    frac = cloud_fraction_estimate(rgb)
    assert frac == 1.0


def test_sharpness_score_blur_vs_edge():
    # Uniform / blurred image
    blurred = np.full((100, 100), 0.5, dtype=np.float32)
    s_blur = sharpness_score(blurred)

    # Sharp checkered image
    sharp = np.indices((100, 100)).sum(axis=0) % 2
    s_sharp = sharpness_score(sharp.astype(np.float32))

    assert s_blur == 0.0
    assert s_sharp > 0.5


def test_false_alarm_suppression_cloudy_pair():
    # Raw change score is high (0.85), but before observation is 80% cloudy
    before_q = ObservationQuality(
        cloud_fraction=0.80, valid_pixel_fraction=1.0, sharpness=0.5, quality_score=0.2
    )
    after_q = ObservationQuality(
        cloud_fraction=0.05, valid_pixel_fraction=1.0, sharpness=0.8, quality_score=0.9
    )

    res = evaluate(
        raw_change_score=0.85,
        before_q=before_q,
        after_q=after_q,
        registration_correlation=0.9,
        radiometric_diff=0.1,
    )

    # Change score and confidence should be heavily discounted due to cloud contamination
    assert res.change_score < 0.30
    assert any("cloud" in r.lower() for r in res.reasons)


def test_false_alarm_suppression_clean_change():
    # High quality, no clouds, strong correlation, true ground change
    before_q = ObservationQuality(
        cloud_fraction=0.02, valid_pixel_fraction=1.0, sharpness=0.85, quality_score=0.95
    )
    after_q = ObservationQuality(
        cloud_fraction=0.01, valid_pixel_fraction=1.0, sharpness=0.88, quality_score=0.96
    )

    res = evaluate(
        raw_change_score=0.80,
        before_q=before_q,
        after_q=after_q,
        registration_correlation=0.92,
        radiometric_diff=0.05,
    )

    assert res.change_score >= 0.75
    assert res.confidence >= 0.75
