"""
Verification suite for the multi-evidence change pipeline.

Covers each stage of

    before + after -> registration -> radiometric normalization
    -> cloud/quality masking -> EO features -> deep feature difference
    -> spectral differences -> spatial/context consistency -> evidence fusion
    -> false-alarm suppression -> change mask -> change type -> confidence

and, most importantly, the properties that motivated replacing the single
embedding-difference score:
  * an unchanged pair must score near zero (min-max normalisation could not),
  * a single loud evidence layer must not raise a detection on its own,
  * cloud, shadow and nodata pixels must never produce change,
  * a real bi-temporal scene pair must still be detected and typed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import numpy as np
import pytest

from services.algorithms.evidence import (
    EvidenceLayer,
    deep_feature_difference,
    robust_probability,
    spatial_evidence,
    spectral_evidence,
)
from services.algorithms.fusion import CORROBORATION_FLOOR, fuse_evidence
from services.algorithms.imageops import box_mean, remove_small_regions, resize_to
from services.algorithms.masking import compute_quality_mask, joint_valid_mask
from services.algorithms.normalization import normalize_relative_radiometry
from services.algorithms.pipeline import Observation, analyze_change_pair
from services.algorithms.spectral import compute_spectral_indices
from services.algorithms.suppression import suppress_false_alarms
from services.false_alarm import ObservationQuality, evaluate

BANDS = {"blue": 0, "green": 1, "red": 2, "nir": 3, "swir1": 4, "swir2": 5}


# ---------------------------------------------------------------------------
# Fixtures — synthetic six-band scenes with a known, localised change
# ---------------------------------------------------------------------------
def _terrain(size: int, seed: int, cells: int = 8) -> np.ndarray:
    """
    A smooth [0, 1] field standing in for land-cover structure.

    Real tiles vary over tens of metres — field boundaries, canopy, roads — not
    pixel to pixel. Co-registration needs that structure to lock onto, so a
    fixture made of per-pixel noise alone would test nothing.
    """
    rng = np.random.default_rng(seed)
    coarse = rng.uniform(0.0, 1.0, (cells, cells)).astype(np.float32)
    return resize_to(coarse, size, size)


def _vegetated_scene(size: int = 128, seed: int = 7) -> np.ndarray:
    """A vegetated tile: high NIR, low SWIR, field-scale structure plus grain."""
    rng = np.random.default_rng(seed)
    structure = _terrain(size, seed)
    field = _terrain(size, seed + 1, cells=4)
    scene = np.zeros((size, size, 6), dtype=np.float32)
    scene[..., 0] = 0.05 + 0.03 * structure + rng.normal(0, 0.004, (size, size))   # blue
    scene[..., 1] = 0.07 + 0.05 * structure + rng.normal(0, 0.005, (size, size))   # green
    scene[..., 2] = 0.05 + 0.05 * structure + rng.normal(0, 0.005, (size, size))   # red
    scene[..., 3] = 0.30 + 0.22 * field + rng.normal(0, 0.015, (size, size))       # nir
    scene[..., 4] = 0.13 + 0.10 * field + rng.normal(0, 0.008, (size, size))       # swir1
    scene[..., 5] = 0.08 + 0.07 * field + rng.normal(0, 0.006, (size, size))       # swir2
    return np.clip(scene, 0.0, 1.0)


def _add_construction(scene: np.ndarray, box=(40, 40, 36, 36)) -> np.ndarray:
    """Replace a block with a built-up signature: NIR collapses, SWIR rises."""
    out = scene.copy()
    y, x, h, w = box
    rng = np.random.default_rng(11)
    out[y:y + h, x:x + w, 0] = 0.20
    out[y:y + h, x:x + w, 1] = 0.22
    out[y:y + h, x:x + w, 2] = 0.26
    out[y:y + h, x:x + w, 3] = 0.24
    out[y:y + h, x:x + w, 4] = 0.38
    out[y:y + h, x:x + w, 5] = 0.34
    # Built structure is texturally busy, unlike a uniform field.
    out[y:y + h, x:x + w] += rng.normal(0, 0.02, (h, w, 6)).astype(np.float32)
    return np.clip(out, 0.0, 1.0)


def _observation(scene: np.ndarray, **kwargs) -> Observation:
    return Observation(raster=scene, band_map=BANDS, **kwargs)


def _fake_extractor(patch: int = 8):
    """
    A deterministic stand-in for Prithvi: per-patch band means and standard
    deviations. Real enough to react to genuine change, cheap enough for tests.
    """

    def extractor(raster, band_map):
        h, w, c = raster.shape
        ph, pw = max(h // patch, 1), max(w // patch, 1)
        feats = np.zeros((ph, pw, c * 2), dtype=np.float32)
        for i in range(ph):
            for j in range(pw):
                block = raster[i * patch:(i + 1) * patch, j * patch:(j + 1) * patch]
                flat = block.reshape(-1, c)
                feats[i, j] = np.concatenate([flat.mean(axis=0), flat.std(axis=0)])
        return feats, "test-extractor", False

    return extractor


# ---------------------------------------------------------------------------
# Calibration — the property min-max normalisation could not deliver
# ---------------------------------------------------------------------------
def test_robust_probability_is_zero_without_real_difference():
    """A difference map entirely below the floor must not produce detections."""
    diff = np.full((32, 32), 0.001, dtype=np.float32)
    diff[5, 5] = 0.004  # the scene maximum, but still tiny in absolute terms
    prob = robust_probability(diff, floor=0.02, scale=0.2)
    assert prob.max() == pytest.approx(0.0, abs=1e-6)


def test_robust_probability_detects_uniform_change():
    """A whole-tile change has no scene-relative outlier, yet must still score."""
    diff = np.full((32, 32), 0.25, dtype=np.float32)
    prob = robust_probability(diff, floor=0.02, scale=0.2)
    assert prob.min() > 0.45


def test_robust_probability_rises_with_magnitude():
    small = robust_probability(np.full((16, 16), 0.05, dtype=np.float32), 0.02, 0.2)
    large = robust_probability(np.full((16, 16), 0.30, dtype=np.float32), 0.02, 0.2)
    assert large.mean() > small.mean()


# ---------------------------------------------------------------------------
# Deep feature difference
# ---------------------------------------------------------------------------
def test_deep_feature_difference_identical_is_zero():
    rng = np.random.default_rng(3)
    feats = rng.normal(size=(8, 8, 32)).astype(np.float32)
    cosine, magnitude = deep_feature_difference(feats, feats)
    assert cosine.max() < 1e-5
    assert magnitude.max() < 1e-5


def test_deep_feature_difference_is_gain_invariant():
    """Cosine distance must ignore a pure activation rescale."""
    rng = np.random.default_rng(3)
    feats = rng.normal(size=(8, 8, 32)).astype(np.float32)
    cosine, magnitude = deep_feature_difference(feats, feats * 2.0)
    assert cosine.max() < 1e-5
    assert magnitude.mean() > 0.4  # …while the magnitude term still sees it


def test_deep_feature_difference_rejects_mismatched_feature_spaces():
    with pytest.raises(ValueError, match="feature shapes do not match"):
        deep_feature_difference(np.zeros((4, 4, 768), np.float32), np.zeros((4, 4, 7), np.float32))


# ---------------------------------------------------------------------------
# Cloud / quality masking
# ---------------------------------------------------------------------------
def test_quality_mask_from_scl_codes():
    scene = _vegetated_scene(64)
    scl = np.full((64, 64), 4, dtype=np.int32)      # vegetation
    scl[10:20, 10:20] = 9                            # cloud high probability
    scl[40:45, 40:45] = 3                            # cloud shadow
    mask = compute_quality_mask(scene, BANDS, scl=scl, dilation=0)
    assert mask.method == "scl"
    assert mask.cloud[15, 15] and not mask.valid[15, 15]
    assert mask.shadow[42, 42] and not mask.valid[42, 42]
    assert mask.valid[0, 0]
    assert mask.clear_fraction < 1.0


def test_quality_mask_dilates_cloud_halo():
    scene = _vegetated_scene(64)
    scl = np.full((64, 64), 4, dtype=np.int32)
    scl[30:34, 30:34] = 8
    tight = compute_quality_mask(scene, BANDS, scl=scl, dilation=0)
    grown = compute_quality_mask(scene, BANDS, scl=scl, dilation=3)
    assert grown.cloud.sum() > tight.cloud.sum()
    assert not grown.valid[28, 30]  # halo pixel excluded


def test_quality_mask_heuristic_flags_bright_lowsat_pixels():
    scene = _vegetated_scene(64)
    scene[5:15, 5:15, :] = 0.85  # bright, unsaturated => cloud-like
    mask = compute_quality_mask(scene, BANDS, dilation=0)
    assert mask.method.startswith("heuristic")
    assert mask.cloud[10, 10]


def test_quality_mask_keeps_uniformly_dark_scene():
    """
    A dark tile (open water, dense canopy, winter light) is not shadow.

    An absolute darkness threshold masks such a scene out entirely and the
    detector then has nothing to compare, so the cut-off is scene-relative.
    """
    scene = _vegetated_scene(64) * 0.02  # everything far below any absolute cut-off
    mask = compute_quality_mask(scene, {"red": 0, "green": 1, "blue": 2}, dilation=0)
    assert mask.clear_fraction > 0.9
    assert mask.shadow_fraction < 0.1


def test_quality_mask_still_finds_relative_shadow():
    """A genuinely dark patch against a brighter scene is still flagged."""
    scene = _vegetated_scene(64)
    scene[20:30, 20:30] *= 0.05
    mask = compute_quality_mask(scene, {"red": 0, "green": 1, "blue": 2}, dilation=0)
    assert mask.shadow[25, 25]
    assert mask.valid[50, 50]


def test_joint_valid_mask_intersects_both_dates():
    scene = _vegetated_scene(32)
    scl_a = np.full((32, 32), 4, dtype=np.int32)
    scl_a[0:8, :] = 9
    scl_b = np.full((32, 32), 4, dtype=np.int32)
    scl_b[:, 0:8] = 9
    a = compute_quality_mask(scene, BANDS, scl=scl_a, dilation=0)
    b = compute_quality_mask(scene, BANDS, scl=scl_b, dilation=0)
    joint = joint_valid_mask(a, b)
    assert not joint[2, 20] and not joint[20, 2]
    assert joint[20, 20]


# ---------------------------------------------------------------------------
# Radiometric normalization
# ---------------------------------------------------------------------------
def test_pif_normalization_removes_gain_and_offset():
    before = _vegetated_scene(96)
    after = np.clip(before * 1.25 + 0.04, 0.0, 1.0)
    result = normalize_relative_radiometry(after, before)
    assert result.method == "pif-linear"
    assert result.shift_after < result.shift_before * 0.5
    assert np.allclose(np.asarray(result.gains[:3]), 0.8, atol=0.15)


def test_pif_normalization_preserves_real_change():
    """The gain/offset fit must not normalise a genuine change region away."""
    before = _vegetated_scene(128)
    after = _add_construction(np.clip(before * 1.15 + 0.03, 0.0, 1.0))
    result = normalize_relative_radiometry(after, before)
    changed = result.array[50:70, 50:70, 4].mean()   # SWIR1 inside construction
    background = result.array[5:25, 5:25, 4].mean()
    assert changed > background + 0.10


# ---------------------------------------------------------------------------
# Evidence fusion
# ---------------------------------------------------------------------------
def _layer(name, value, weight=0.33, reliability=1.0, shape=(8, 8)):
    return EvidenceLayer(
        name=name,
        probability=np.full(shape, value, dtype=np.float32),
        weight=weight,
        reliability=reliability,
        detail="test layer",
    )


def test_fusion_damps_single_layer_evidence():
    """One loud layer against two quiet ones must not clear the threshold."""
    layers = [
        _layer("deep_feature", 0.95, 0.45),
        _layer("spectral", 0.10, 0.35),
        _layer("spatial_context", 0.10, 0.20),
    ]
    fused = fuse_evidence(layers)
    assert fused.probability.max() < 0.5


def test_fusion_keeps_corroborated_evidence():
    layers = [
        _layer("deep_feature", 0.90, 0.45),
        _layer("spectral", 0.85, 0.35),
        _layer("spatial_context", 0.80, 0.20),
    ]
    fused = fuse_evidence(layers)
    assert fused.probability.min() > 0.75
    assert fused.agreement.mean() == pytest.approx(1.0)


def test_fusion_downweights_unreliable_layer():
    """A layer flagged unreliable contributes proportionally less."""
    trusted = fuse_evidence([_layer("deep_feature", 0.9, 0.45, reliability=1.0), _layer("spectral", 0.1, 0.35)])
    doubted = fuse_evidence([_layer("deep_feature", 0.9, 0.45, reliability=0.5), _layer("spectral", 0.1, 0.35)])
    assert doubted.probability.mean() < trusted.probability.mean()
    assert doubted.weights["deep_feature"] < trusted.weights["deep_feature"]


def test_fusion_corroboration_floor_is_applied():
    layers = [_layer("a", 0.8, 0.5), _layer("b", 0.0, 0.5)]
    fused = fuse_evidence(layers)
    expected = 0.4 * (CORROBORATION_FLOOR + (1 - CORROBORATION_FLOOR) * 0.5)
    assert fused.probability.mean() == pytest.approx(expected, abs=1e-5)


def test_fusion_rejects_mismatched_layer_shapes():
    with pytest.raises(ValueError, match="expected"):
        fuse_evidence([_layer("a", 0.5, shape=(8, 8)), _layer("b", 0.5, shape=(4, 4))])


# ---------------------------------------------------------------------------
# Per-pixel false-alarm suppression
# ---------------------------------------------------------------------------
def test_suppression_zeroes_masked_pixels():
    prob = np.full((64, 64), 0.9, dtype=np.float32)
    valid = np.ones((64, 64), dtype=bool)
    valid[10:30, 10:30] = False
    result = suppress_false_alarms(prob, valid, _vegetated_scene(64), threshold=0.5)
    assert result.mask[20, 20] == 0
    assert result.mask[50, 50] == 1
    assert result.stages[0]["stage"] == "quality_masking"


def test_suppression_removes_speckle():
    """Isolated single-pixel detections must not survive to the change mask."""
    prob = np.zeros((64, 64), dtype=np.float32)
    rng = np.random.default_rng(5)
    ys = rng.integers(0, 64, 25)
    xs = rng.integers(0, 64, 25)
    prob[ys, xs] = 0.95
    prob[40:50, 40:50] = 0.95  # one genuine, contiguous blob
    result = suppress_false_alarms(
        prob, np.ones((64, 64), bool), _vegetated_scene(64), threshold=0.5, min_region_pixels=8
    )
    assert result.mask[44, 44] == 1
    assert result.mask.sum() < 130  # the blob, not the blob plus 25 specks


def test_suppression_discounts_edges_under_registration_residual():
    """With residual misalignment, change on strong edges is discounted."""
    scene = _vegetated_scene(64)
    scene[:, 32:] += 0.3  # a hard vertical edge
    scene = np.clip(scene, 0, 1)
    prob = np.full((64, 64), 0.62, dtype=np.float32)
    aligned = suppress_false_alarms(prob, None, scene, threshold=0.5, residual_shift_px=0.0)
    misaligned = suppress_false_alarms(prob, None, scene, threshold=0.5, residual_shift_px=1.8)
    assert misaligned.probability[32, 32] < aligned.probability[32, 32]
    assert misaligned.mask.sum() < aligned.mask.sum()


def test_suppression_edge_penalty_ignores_inter_date_correlation():
    """
    A well-aligned pair with large genuine change must not be edge-suppressed.
    Correlation between dates falls with real change, so only the measured
    post-warp residual may drive the penalty.
    """
    scene = _vegetated_scene(64)
    scene[:, 32:] += 0.3
    scene = np.clip(scene, 0, 1)
    prob = np.full((64, 64), 0.7, dtype=np.float32)
    result = suppress_false_alarms(
        prob, None, scene, threshold=0.5, residual_shift_px=0.0, registration_aligned=True
    )
    stage = next(s for s in result.stages if s["stage"] == "registration_residual")
    assert stage["pixels_removed"] == 0


def test_suppression_penalises_unregistered_pair():
    scene = _vegetated_scene(64)
    scene[:, 32:] += 0.3
    scene = np.clip(scene, 0, 1)
    prob = np.full((64, 64), 0.62, dtype=np.float32)
    aligned = suppress_false_alarms(prob, None, scene, threshold=0.5, registration_aligned=True)
    unaligned = suppress_false_alarms(prob, None, scene, threshold=0.5, registration_aligned=False)
    assert unaligned.mask.sum() < aligned.mask.sum()


def test_suppression_reports_every_stage():
    result = suppress_false_alarms(
        np.full((32, 32), 0.7, np.float32), np.ones((32, 32), bool), _vegetated_scene(32)
    )
    names = [stage["stage"] for stage in result.stages]
    assert names == [
        "quality_masking",
        "registration_residual",
        "context_corroboration",
        "morphological_cleanup",
    ]


# ---------------------------------------------------------------------------
# Scene-level scoring
# ---------------------------------------------------------------------------
def _clean_quality():
    return ObservationQuality(
        cloud_fraction=0.02, valid_pixel_fraction=0.98, sharpness=0.9, quality_score=0.95
    )


def test_scene_score_judges_alignment_on_residual_not_correlation():
    """
    A well-registered pair whose dates correlate poorly *because a lot really
    changed* must not be written off as a misalignment artefact.
    """
    result = evaluate(
        raw_change_score=0.85,
        before_q=_clean_quality(),
        after_q=_clean_quality(),
        registration_correlation=0.35,      # depressed by the change itself
        radiometric_diff=0.05,
        registration_residual_px=0.11,      # …yet the geometry is sound
        registration_aligned=True,
    )
    assert not [c for c in result.confounds if c.factor == "poor_registration"]
    assert result.change_score >= 0.85


def test_scene_score_still_penalises_measured_misalignment():
    result = evaluate(
        raw_change_score=0.85,
        before_q=_clean_quality(),
        after_q=_clean_quality(),
        registration_correlation=0.95,      # flattering, and beside the point
        radiometric_diff=0.05,
        registration_residual_px=2.4,
        registration_aligned=False,
    )
    confound = [c for c in result.confounds if c.factor == "poor_registration"]
    assert confound and confound[0].severity == "high"
    assert result.change_score < 0.4


def test_scene_score_rewards_corroboration_without_saturating():
    """Corroboration boosts consume headroom; it must not pin the scale at 1.0."""
    result = evaluate(
        raw_change_score=0.86,
        before_q=_clean_quality(),
        after_q=_clean_quality(),
        registration_correlation=0.95,
        radiometric_diff=0.05,
        temporal_series=[0.8, 0.82, 0.79],
        evidence_agreement=0.96,
        evidence_layers=[{"name": "deep_feature"}, {"name": "spectral"}, {"name": "spatial_context"}],
        clear_fraction=1.0,
        registration_residual_px=0.1,
        registration_aligned=True,
    )
    assert 0.86 < result.change_score < 1.0
    assert result.confidence > 0.8


def test_scene_score_flags_single_evidence_source():
    result = evaluate(
        raw_change_score=0.8,
        before_q=_clean_quality(),
        after_q=_clean_quality(),
        registration_correlation=0.95,
        radiometric_diff=0.05,
        evidence_agreement=0.12,
        evidence_layers=[{"name": "deep_feature"}, {"name": "spectral"}, {"name": "spatial_context"}],
    )
    assert [c for c in result.confounds if c.factor == "single_evidence_source"]
    assert result.change_score < 0.8


def test_scene_score_flags_masked_coverage():
    result = evaluate(
        raw_change_score=0.8,
        before_q=_clean_quality(),
        after_q=_clean_quality(),
        registration_correlation=0.95,
        radiometric_diff=0.05,
        clear_fraction=0.2,
    )
    confound = [c for c in result.confounds if c.factor == "masked_coverage"]
    assert confound and confound[0].severity == "high"


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------
def test_pipeline_finds_no_change_in_identical_pair():
    scene = _vegetated_scene(128)
    analysis = analyze_change_pair(
        _observation(scene), _observation(scene.copy()), feature_extractor=_fake_extractor()
    )
    assert analysis.changed_fraction < 0.01
    assert analysis.raw_change_score < 0.2
    assert analysis.dominant_change_type == "no_significant_change"


def test_pipeline_rejects_pure_illumination_shift():
    """
    A brightened, gain-shifted copy is the classic false alarm. Normalization
    plus the illumination-invariant spatial layer must reject it.
    """
    before = _vegetated_scene(128)
    after = np.clip(before * 1.3 + 0.06, 0.0, 1.0)
    analysis = analyze_change_pair(
        _observation(before), _observation(after), feature_extractor=_fake_extractor()
    )
    assert analysis.changed_fraction < 0.05


def test_pipeline_detects_and_types_construction():
    before = _vegetated_scene(128)
    after = _add_construction(before)
    analysis = analyze_change_pair(
        _observation(before), _observation(after), feature_extractor=_fake_extractor()
    )

    assert analysis.changed_fraction > 0.02
    assert analysis.dominant_change_type in ("construction", "clearance", "road_development")
    assert analysis.regions
    # The change must land where it was planted, not smeared across the tile.
    biggest = max(analysis.regions, key=lambda r: r.area_pixels)
    cx, cy = biggest.centroid
    assert 40 <= cx <= 80 and 40 <= cy <= 80


def test_pipeline_change_survives_illumination_shift():
    """Real change plus a gain shift must still be detected after normalization."""
    before = _vegetated_scene(128)
    after = _add_construction(np.clip(before * 1.2 + 0.04, 0.0, 1.0))
    analysis = analyze_change_pair(
        _observation(before), _observation(after), feature_extractor=_fake_extractor()
    )
    assert analysis.changed_fraction > 0.01


def test_pipeline_never_reports_change_under_cloud():
    """Cloud over the changed area must suppress it, not detect it."""
    before = _vegetated_scene(128)
    after = _add_construction(before)
    scl = np.full((128, 128), 4, dtype=np.int32)
    scl[35:85, 35:85] = 9  # cloud covering the construction site
    analysis = analyze_change_pair(
        _observation(before),
        _observation(after, scl=scl),
        feature_extractor=_fake_extractor(),
    )
    assert analysis.change_mask[60, 60] == 0
    assert analysis.clear_fraction < 1.0


def test_pipeline_runs_every_stage_in_order():
    before = _vegetated_scene(128)
    after = _add_construction(before)
    analysis = analyze_change_pair(
        _observation(before), _observation(after), feature_extractor=_fake_extractor()
    )
    assert [stage.name for stage in analysis.stages] == [
        "registration",
        "quality_masking",
        "radiometric_normalization",
        "deep_feature_difference",
        "spectral_difference",
        "spatial_context_consistency",
        "evidence_fusion",
        "false_alarm_suppression",
        "change_mask",
        "change_typing",
    ]
    assert all(stage.detail for stage in analysis.stages)


def test_pipeline_fuses_three_independent_layers():
    before = _vegetated_scene(128)
    after = _add_construction(before)
    analysis = analyze_change_pair(
        _observation(before), _observation(after), feature_extractor=_fake_extractor()
    )
    assert [layer.name for layer in analysis.layers] == ["deep_feature", "spectral", "spatial_context"]
    summaries = analysis.layer_summaries()
    assert len(summaries) == 3
    assert all("mean_probability" in s and "reliability" in s for s in summaries)
    assert sum(analysis.fusion.weights.values()) == pytest.approx(1.0)


def test_pipeline_degrades_without_feature_extractor():
    """Without an EO backbone, spectral + spatial evidence must still work."""
    before = _vegetated_scene(128)
    after = _add_construction(before)
    analysis = analyze_change_pair(_observation(before), _observation(after), feature_extractor=None)
    assert not analysis.deep_available
    assert [layer.name for layer in analysis.layers] == ["spectral", "spatial_context"]
    assert analysis.changed_fraction > 0.01
    skipped = [s for s in analysis.stages if s.name == "deep_feature_difference"]
    assert skipped and skipped[0].status == "skipped"


def test_pipeline_survives_failing_feature_extractor():
    def broken(raster, band_map):
        raise RuntimeError("model unavailable")

    before = _vegetated_scene(96)
    analysis = analyze_change_pair(
        _observation(before), _observation(_add_construction(before)), feature_extractor=broken
    )
    stage = next(s for s in analysis.stages if s.name == "deep_feature_difference")
    assert stage.status == "skipped"
    assert "model unavailable" in stage.detail


def test_pipeline_downweights_rgb_only_spectral_evidence():
    rng = np.random.default_rng(1)
    before = np.clip(rng.uniform(0.2, 0.5, (96, 96, 3)).astype(np.float32), 0, 1)
    after = before.copy()
    after[30:60, 30:60] = 0.8
    rgb_map = {"red": 0, "green": 1, "blue": 2}
    analysis = analyze_change_pair(
        Observation(raster=before, band_map=rgb_map),
        Observation(raster=after, band_map=rgb_map),
        feature_extractor=_fake_extractor(),
    )
    spectral = next(layer for layer in analysis.layers if layer.name == "spectral")
    assert spectral.reliability < 1.0
    assert not spectral.stats["is_multispectral"]


def test_pipeline_region_confidence_reflects_evidence_agreement():
    before = _vegetated_scene(128)
    after = _add_construction(before)
    analysis = analyze_change_pair(
        _observation(before), _observation(after), feature_extractor=_fake_extractor()
    )
    stage = next(s for s in analysis.stages if s.name == "change_typing")
    evidence = stage.metrics["region_evidence"]
    assert evidence
    for entry in evidence.values():
        assert {"deep_feature", "spectral", "spatial_context", "agreement"} <= set(entry)
    assert all(0.0 <= region.confidence <= 1.0 for region in analysis.regions)


# ---------------------------------------------------------------------------
# Real bi-temporal scenes, when the sample data is present
# ---------------------------------------------------------------------------
def _load_scene(path):
    import rasterio

    from services.ingestion import _resolve_band_map

    with rasterio.open(path) as ds:
        bands = ds.read().astype(np.float32)
        band_map = {k: v - 1 for k, v in _resolve_band_map(ds, "Sentinel-2").items() if v <= ds.count}
    raster = np.transpose(bands, (1, 2, 0))
    if raster.max() > 1.0:
        raster = raster / (255.0 if raster.max() <= 255.0 else 10000.0)
    return raster.astype(np.float32), band_map


def test_pipeline_on_real_bitemporal_scene_pair():
    """
    Accuracy against an independent reference on the real demo scene pair.

    The reference is a plain spectral-index threshold (NDBI up or NDVI down) —
    a detector built on different logic from the fused pipeline, so agreeing
    with it is evidence the pipeline finds the change that is actually there
    and puts it in the right place.
    """
    incoming = Path(__file__).resolve().parent.parent / "data" / "incoming"
    before_path = incoming / "Sentinel-2_20230101_demoAOI.tif"
    after_path = incoming / "Sentinel-2_20240101_demoAOI.tif"
    if not before_path.exists() or not after_path.exists():
        pytest.skip("Sample scenes not staged")

    before_raster, before_map = _load_scene(before_path)
    after_raster, after_map = _load_scene(after_path)

    analysis = analyze_change_pair(
        Observation(raster=before_raster, band_map=before_map),
        Observation(raster=after_raster, band_map=after_map),
        feature_extractor=_fake_extractor(16),
    )

    before_indices = compute_spectral_indices(before_raster, before_map)
    after_indices = compute_spectral_indices(after_raster, after_map)
    reference = (after_indices.ndbi - before_indices.ndbi > 0.05) | (
        after_indices.ndvi - before_indices.ndvi < -0.10
    )
    detected = analysis.change_mask.astype(bool)
    overlap = int((detected & reference).sum())

    recall = overlap / max(int(reference.sum()), 1)
    precision = overlap / max(int(detected.sum()), 1)
    assert recall > 0.7, f"missed most of the reference change (recall={recall:.2f})"
    assert precision > 0.6, f"detected change the reference does not support (precision={precision:.2f})"

    assert analysis.regions
    assert analysis.dominant_change_type != "no_significant_change"
    # Corroboration is measured inside the detection, so a real change must
    # show most of its evidence weight agreeing there.
    assert analysis.evidence_agreement > 0.5
    assert analysis.clear_fraction > 0.5


def test_pipeline_self_comparison_on_real_scene_is_quiet():
    """The same real scene against itself must produce no change at all."""
    incoming = Path(__file__).resolve().parent.parent / "data" / "incoming"
    scene_path = incoming / "Sentinel-2_20230101_demoAOI.tif"
    if not scene_path.exists():
        pytest.skip("Sample scenes not staged")

    raster, band_map = _load_scene(scene_path)
    size = min(256, raster.shape[0], raster.shape[1])
    raster = raster[:size, :size]
    analysis = analyze_change_pair(
        Observation(raster=raster, band_map=band_map),
        Observation(raster=raster.copy(), band_map=band_map),
        feature_extractor=_fake_extractor(16),
    )
    assert analysis.changed_fraction < 0.005


# ---------------------------------------------------------------------------
# Shared image operators
# ---------------------------------------------------------------------------
def test_box_mean_matches_bruteforce():
    rng = np.random.default_rng(0)
    arr = rng.uniform(size=(21, 17)).astype(np.float32)
    got = box_mean(arr, 2)
    for y, x in ((0, 0), (10, 8), (20, 16)):
        window = arr[max(y - 2, 0):y + 3, max(x - 2, 0):x + 3]
        assert got[y, x] == pytest.approx(window.mean(), abs=1e-5)


def test_box_mean_honours_mask():
    arr = np.ones((9, 9), dtype=np.float32)
    arr[4, 4] = 100.0
    mask = np.ones((9, 9), dtype=bool)
    mask[4, 4] = False
    assert box_mean(arr, 2, mask)[4, 4] == pytest.approx(1.0, abs=1e-5)


def test_remove_small_regions_keeps_large_blobs():
    mask = np.zeros((32, 32), dtype=bool)
    mask[2, 2] = True
    mask[10:16, 10:16] = True
    kept = remove_small_regions(mask, 9)
    assert not kept[2, 2]
    assert kept[12, 12]


def test_resize_to_preserves_channels():
    arr = np.zeros((8, 8, 5), dtype=np.float32)
    assert resize_to(arr, 16, 16).shape == (16, 16, 5)
    assert resize_to(arr[..., 0], 4, 4).shape == (4, 4)
