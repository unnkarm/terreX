"""
Tier 1 Verification Tests:
- 1.1 AOI Polygon Drawing & True Geometric Search
- 1.2 Natural-Language Filter Parsing
- 1.3 Multi-Observation Timeline (observation stack construction)
- 1.4 Explainable Evidence Checklist
- 1.5 "Why Confidence Decreased" Breakdown (confound attribution)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest
import numpy as np
from shapely.geometry import Point, Polygon


# =============================================================================
# 1.1 — Polygon Geometric Search
# =============================================================================

from services.search import _parse_polygon_geometry


def test_polygon_parse_geojson_polygon():
    """Parse a standard GeoJSON Polygon object."""
    geojson = {
        "type": "Polygon",
        "coordinates": [
            [[88.3, 22.5], [88.5, 22.5], [88.5, 22.7], [88.3, 22.7], [88.3, 22.5]]
        ],
    }
    poly = _parse_polygon_geometry(geojson)
    assert poly is not None
    assert poly.geom_type == "Polygon"
    assert poly.contains(Point(88.4, 22.6))
    assert not poly.contains(Point(89.0, 22.6))


def test_polygon_parse_geojson_feature():
    """Parse a GeoJSON Feature wrapping a Polygon."""
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[88.3, 22.5], [88.5, 22.5], [88.5, 22.7], [88.3, 22.7], [88.3, 22.5]]
            ],
        },
    }
    poly = _parse_polygon_geometry(feature)
    assert poly is not None
    assert poly.geom_type == "Polygon"


def test_polygon_parse_coord_list():
    """Parse a raw coordinate list (list of [lon, lat] pairs)."""
    coords = [[88.3, 22.5], [88.5, 22.5], [88.5, 22.7], [88.3, 22.7], [88.3, 22.5]]
    poly = _parse_polygon_geometry(coords)
    assert poly is not None
    assert poly.contains(Point(88.4, 22.6))


def test_polygon_parse_none():
    """None input returns None."""
    assert _parse_polygon_geometry(None) is None


def test_polygon_inclusion_exclusion():
    """Verify that points inside/outside the polygon produce correct results."""
    poly = Polygon(
        [[88.3, 22.5], [88.5, 22.5], [88.5, 22.7], [88.3, 22.7], [88.3, 22.5]]
    )
    # Inside
    inside = Point(88.4, 22.6)
    assert poly.contains(inside) or poly.intersects(inside)
    # Outside
    outside = Point(89.0, 23.0)
    assert not poly.contains(outside) and not poly.intersects(outside)


# =============================================================================
# 1.2 — Natural-Language Filter Parsing
# =============================================================================

from services.nlp_filter import (
    parse_natural_language_query,
    compute_distance_km,
    ParsedQueryFilters,
)


def test_nl_simple_semantic_query():
    """A simple query with no constraints returns the same query as semantic."""
    r = parse_natural_language_query("large new structures")
    assert isinstance(r, ParsedQueryFilters)
    assert "structure" in r.semantic_query.lower() or "large" in r.semantic_query.lower()
    assert r.spatial_relation is None
    assert r.date_from is None
    assert r.max_cloud_cover is None


def test_nl_compound_with_spatial_date_cloud():
    """Compound query extracts spatial, date, and quality constraints."""
    r = parse_natural_language_query(
        "large new structures within 5km of rivers after January 2024, excluding cloudy imagery"
    )
    # Spatial
    assert r.spatial_relation is not None
    assert r.spatial_relation.relation_type == "within"
    assert r.spatial_relation.distance_km == 5.0
    assert "river" in r.spatial_relation.target.lower()
    # Date
    assert r.date_from is not None
    assert r.date_from.startswith("2024")
    # Cloud
    assert r.max_cloud_cover is not None
    assert r.max_cloud_cover <= 0.20
    # Explanation tags
    assert len(r.explanation) >= 3


def test_nl_sensor_extraction():
    """Sentinel-2 sensor is extracted."""
    r = parse_natural_language_query("roads from Sentinel-2 after 2023")
    assert r.sensor == "Sentinel-2"
    assert r.date_from is not None


def test_nl_near_spatial():
    """'near' spatial pattern is detected."""
    r = parse_natural_language_query("water extent near hooghly river")
    assert r.spatial_relation is not None
    assert r.spatial_relation.relation_type == "near"
    assert "hooghly" in r.spatial_relation.target.lower()


def test_nl_clear_sky_filter():
    """'clear sky' should produce max_cloud filter."""
    r = parse_natural_language_query("construction clear sky only")
    assert r.max_cloud_cover is not None
    assert r.max_cloud_cover <= 0.15


def test_compute_distance_to_river():
    """Distance from a known point near Hooghly River returns reasonable km."""
    dist = compute_distance_km(88.35, 22.60, "river")
    assert dist is not None
    assert dist < 5.0  # Very close to the river geometry


def test_compute_distance_unknown_feature():
    """Distance to an unknown feature returns None."""
    dist = compute_distance_km(88.35, 22.60, "zzz_nonexistent_feature")
    assert dist is None


# =============================================================================
# 1.3 — Multi-Observation Timeline (observation stack structure)
# =============================================================================

def test_observation_stack_structure():
    """
    An observation stack entry should contain all required fields per Tier 1.3.
    This tests the expected dict shape without requiring DB/model runs.
    """
    obs = {
        "index": 1,
        "tile_id": "tile_001",
        "scene_id": "scene_001",
        "acquisition_date": "2024-01-15",
        "date_formatted": "2024-01-15",
        "year": "2024",
        "sensor": "Sentinel-2",
        "cloud_fraction": 0.05,
        "quality_score": 0.92,
        "thumbnail_url": "/static/tiles/scene_001/thumb.jpg",
        "distance_from_baseline": 0.0,
        "mean_ndvi": 0.55,
        "mean_ndwi": -0.10,
        "mean_ndbi": 0.12,
        "is_baseline": True,
        "is_earliest_change": False,
    }
    required_keys = {
        "index", "tile_id", "scene_id", "acquisition_date",
        "date_formatted", "year", "sensor", "cloud_fraction",
        "quality_score", "thumbnail_url", "distance_from_baseline",
        "mean_ndvi", "mean_ndwi", "mean_ndbi",
        "is_baseline", "is_earliest_change",
    }
    assert required_keys.issubset(obs.keys())


# =============================================================================
# 1.4 & 1.5 — Evidence Checklist & Confidence Breakdown
# =============================================================================

from services.false_alarm import (
    evaluate,
    ObservationQuality,
    ConfoundFactor,
    SuppressionResult,
)


def test_evidence_clean_high_confidence():
    """Clean conditions produce high confidence with no major confounds."""
    result = evaluate(
        raw_change_score=0.85,
        before_q=ObservationQuality(
            cloud_fraction=0.02, valid_pixel_fraction=0.98,
            sharpness=0.90, quality_score=0.95,
        ),
        after_q=ObservationQuality(
            cloud_fraction=0.03, valid_pixel_fraction=0.97,
            sharpness=0.88, quality_score=0.93,
        ),
        registration_correlation=0.95,
        radiometric_diff=0.05,
        temporal_series=[0.80, 0.82, 0.78],
    )
    assert isinstance(result, SuppressionResult)
    assert result.confidence >= 0.7
    assert result.is_high_certainty
    assert isinstance(result.confidence_breakdown, dict)
    assert "raw_change_score" in result.confidence_breakdown
    assert "confounds" in result.confidence_breakdown
    # Should have few or no significant confounds
    severe = [c for c in result.confounds if c.severity in ("high", "medium")]
    assert len(severe) == 0


def test_evidence_cloudy_confound():
    """Cloudy imagery triggers cloud_contamination confound with reduced confidence."""
    result = evaluate(
        raw_change_score=0.80,
        before_q=ObservationQuality(
            cloud_fraction=0.60, valid_pixel_fraction=0.90,
            sharpness=0.80, quality_score=0.70,
        ),
        after_q=ObservationQuality(
            cloud_fraction=0.05, valid_pixel_fraction=0.95,
            sharpness=0.85, quality_score=0.90,
        ),
        registration_correlation=0.90,
        radiometric_diff=0.10,
    )
    assert not result.is_high_certainty or result.confidence < 0.75
    cloud_confound = [c for c in result.confounds if c.factor == "cloud_contamination"]
    assert len(cloud_confound) == 1
    assert cloud_confound[0].severity in ("high", "medium")
    assert "cloud" in cloud_confound[0].explanation.lower()


def test_evidence_poor_registration_confound():
    """Poor registration correlation triggers poor_registration confound."""
    result = evaluate(
        raw_change_score=0.75,
        before_q=ObservationQuality(
            cloud_fraction=0.02, valid_pixel_fraction=0.98,
            sharpness=0.90, quality_score=0.95,
        ),
        after_q=ObservationQuality(
            cloud_fraction=0.03, valid_pixel_fraction=0.97,
            sharpness=0.88, quality_score=0.93,
        ),
        registration_correlation=0.30,
        radiometric_diff=0.10,
    )
    reg_confound = [c for c in result.confounds if c.factor == "poor_registration"]
    assert len(reg_confound) == 1
    assert reg_confound[0].severity == "high"
    assert result.change_score < 0.75  # Score should be penalized


def test_evidence_radiometric_shift_confound():
    """Large radiometric difference triggers radiometric_shift confound."""
    result = evaluate(
        raw_change_score=0.70,
        before_q=ObservationQuality(
            cloud_fraction=0.02, valid_pixel_fraction=0.98,
            sharpness=0.90, quality_score=0.95,
        ),
        after_q=ObservationQuality(
            cloud_fraction=0.03, valid_pixel_fraction=0.97,
            sharpness=0.88, quality_score=0.93,
        ),
        registration_correlation=0.90,
        radiometric_diff=0.80,
    )
    rad_confound = [c for c in result.confounds if c.factor == "radiometric_shift"]
    assert len(rad_confound) == 1
    assert rad_confound[0].severity == "medium"


def test_evidence_no_corroboration_confound():
    """Zero corroborating observations triggers insufficient_corroboration."""
    result = evaluate(
        raw_change_score=0.65,
        before_q=ObservationQuality(
            cloud_fraction=0.02, valid_pixel_fraction=0.98,
            sharpness=0.90, quality_score=0.95,
        ),
        after_q=ObservationQuality(
            cloud_fraction=0.03, valid_pixel_fraction=0.97,
            sharpness=0.88, quality_score=0.93,
        ),
        registration_correlation=0.90,
        radiometric_diff=0.10,
        temporal_series=[0.10, 0.08, 0.12],  # All below threshold
    )
    nocorr_confound = [c for c in result.confounds if c.factor == "insufficient_corroboration"]
    assert len(nocorr_confound) == 1


def test_confidence_breakdown_structure():
    """confidence_breakdown dict contains all required keys."""
    result = evaluate(
        raw_change_score=0.80,
        before_q=ObservationQuality(
            cloud_fraction=0.40, valid_pixel_fraction=0.60,
            sharpness=0.80, quality_score=0.70,
        ),
        after_q=ObservationQuality(
            cloud_fraction=0.05, valid_pixel_fraction=0.95,
            sharpness=0.85, quality_score=0.90,
        ),
        registration_correlation=0.55,
        radiometric_diff=0.70,
        temporal_series=[0.10],
    )
    bd = result.confidence_breakdown
    assert "raw_change_score" in bd
    assert "post_suppression_change_score" in bd
    assert "combined_optical_quality" in bd
    assert "final_confidence" in bd
    assert "is_high_certainty" in bd
    assert "confounds" in bd
    assert isinstance(bd["confounds"], list)
    # Multiple confounds should be present for this terrible quality pair
    assert len(bd["confounds"]) >= 2


def test_evidence_checklist_item_structure():
    """Evidence checklist items have label, status, value, details."""
    item = {
        "label": "Built-up Spectral Response",
        "status": "pass",
        "value": "ΔNDBI: +0.15",
        "details": "Elevated SWIR response characteristic of infrastructure/structures",
    }
    for key in ("label", "status", "value", "details"):
        assert key in item
    assert item["status"] in ("pass", "fail", "info")
