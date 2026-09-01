"""
Unit test suite for TerreX pure-array remote sensing algorithms.

Tests:
1. Spatial co-registration (ORB + affine homography warp)
2. Radiometric normalization (cumulative histogram matching)
3. Multispectral spectral indices (NDVI, NDWI, NDBI) and RGB fallback
4. 2-Layer change typing (Construction, Clearance, Water Extent, Road Development)
"""
import sys
from pathlib import Path

# Add backend to path for tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import numpy as np
import pytest

from services.algorithms.registration import register_image_pair, compute_correlation
from services.algorithms.normalization import normalize_histogram_match
from services.algorithms.spectral import compute_spectral_indices, compute_spectral_deltas, SpectralIndices
from services.algorithms.change_classifier import classify_change_regions


# ---------------------------------------------------------------------------
# 1. Co-Registration Tests
# ---------------------------------------------------------------------------
def test_registration_identical_images():
    # Textured test patch
    rng = np.random.default_rng(42)
    img = rng.uniform(0.2, 0.8, size=(128, 128, 3)).astype(np.float32)
    # Add strong geometric features
    img[30:60, 30:60] = 0.9
    img[70:100, 70:100] = 0.1

    res = register_image_pair(img, img)
    assert res.correlation_before > 0.95
    assert res.aligned_after.shape == img.shape


def test_registration_shifted_image():
    rng = np.random.default_rng(42)
    ref = np.zeros((160, 160, 3), dtype=np.float32)
    # Add strong feature landmarks
    ref[20:50, 20:50] = 0.85
    ref[80:120, 80:120] = 0.15
    ref[40:50, 90:130] = 0.70

    # Shift target by dx=4, dy=3
    dx, dy = 4, 3
    tgt = np.roll(np.roll(ref, dy, axis=0), dx, axis=1)

    corr_unaligned = compute_correlation(ref[..., 0], tgt[..., 0])
    res = register_image_pair(ref, tgt)

    # Co-registration should run and maintain or improve alignment
    assert res.aligned_after.shape == tgt.shape
    assert res.correlation_after >= corr_unaligned - 0.05


def test_registration_noise_graceful_fallback():
    # Pure random noise with no distinct features
    rng = np.random.default_rng(123)
    a = rng.uniform(0, 1, size=(64, 64, 3)).astype(np.float32)
    b = rng.uniform(0, 1, size=(64, 64, 3)).astype(np.float32)

    res = register_image_pair(a, b)
    # Should not crash; should return unaligned copy
    assert res.aligned_after.shape == b.shape
    assert res.is_aligned is False


# ---------------------------------------------------------------------------
# 2. Radiometric Normalization Tests
# ---------------------------------------------------------------------------
def test_radiometric_histogram_matching():
    rng = np.random.default_rng(42)
    # Reference image: mean ~0.7, bright lighting
    ref = rng.normal(0.7, 0.1, size=(100, 100, 3)).clip(0, 1).astype(np.float32)
    # Source image: mean ~0.3, dark/hazy lighting
    src = rng.normal(0.3, 0.1, size=(100, 100, 3)).clip(0, 1).astype(np.float32)

    norm = normalize_histogram_match(src, ref)

    assert norm.shape == src.shape
    # Normalized source mean should shift substantially closer to reference
    assert abs(norm.mean() - ref.mean()) < 0.05
    assert abs(norm.mean() - src.mean()) > 0.25


# ---------------------------------------------------------------------------
# 3. Spectral Index Calculation Tests
# ---------------------------------------------------------------------------
def test_spectral_indices_multispectral():
    # 5-band raster: B, G, R, NIR, SWIR1
    raster = np.zeros((64, 64, 5), dtype=np.float32)
    # Patch 1: Dense Vegetation (High NIR, Low Red)
    raster[0:32, 0:32, 2] = 0.05  # Red: low
    raster[0:32, 0:32, 3] = 0.85  # NIR: high
    # Patch 2: Water (Low NIR, Low SWIR, Moderate Green/Blue)
    raster[0:32, 32:64, 0] = 0.60  # Blue: high
    raster[0:32, 32:64, 1] = 0.50  # Green: moderate
    raster[0:32, 32:64, 3] = 0.02  # NIR: very low
    # Patch 3: Built-up / Bare soil (High SWIR, Moderate NIR/Red)
    raster[32:64, 0:32, 3] = 0.30  # NIR
    raster[32:64, 0:32, 4] = 0.80  # SWIR1: high

    bmap = {"blue": 0, "green": 1, "red": 2, "nir": 3, "swir1": 4}
    indices = compute_spectral_indices(raster, bmap)

    assert indices.is_multispectral is True
    # Vegetation patch should have high positive NDVI (> 0.7)
    assert indices.ndvi[10, 10] > 0.70
    # Water patch should have positive NDWI (> 0.5)
    assert indices.ndwi[10, 45] > 0.50
    # Built-up patch should have high positive NDBI (> 0.3)
    assert indices.ndbi[45, 10] > 0.30


def test_spectral_indices_rgb_fallback():
    rgb = np.zeros((50, 50, 3), dtype=np.float32)
    # Green foliage
    rgb[:, :, 1] = 0.9  # Green
    rgb[:, :, 0] = 0.2  # Red
    rgb[:, :, 2] = 0.2  # Blue

    indices = compute_spectral_indices(rgb)
    assert indices.is_multispectral is False
    assert indices.ndvi.mean() > 0.4  # VARI proxy should be positive


# ---------------------------------------------------------------------------
# 4. 2-Layer Change Classification Tests
# ---------------------------------------------------------------------------
def test_change_typing_construction():
    size = 64
    # Before: Vegetation area
    before_ndvi = np.full((size, size), 0.75, dtype=np.float32)
    before_ndwi = np.full((size, size), -0.5, dtype=np.float32)
    before_ndbi = np.full((size, size), -0.4, dtype=np.float32)
    before_indices = SpectralIndices(before_ndvi, before_ndwi, before_ndbi, True, {})

    # After: Ground cleared and building constructed
    after_ndvi = before_ndvi.copy()
    after_ndwi = before_ndwi.copy()
    after_ndbi = before_ndbi.copy()

    # Square building patch at (20..40, 20..40)
    after_ndvi[20:40, 20:40] = 0.10  # NDVI dropped -0.65
    after_ndbi[20:40, 20:40] = 0.40  # NDBI increased +0.80
    after_indices = SpectralIndices(after_ndvi, after_ndwi, after_ndbi, True, {})

    # Change mask at building location
    change_mask = np.zeros((size, size), dtype=np.uint8)
    change_mask[20:40, 20:40] = 255

    regions = classify_change_regions(change_mask, before_indices, after_indices)
    assert len(regions) == 1
    assert regions[0].change_type == "construction"
    assert regions[0].confidence >= 0.70
    assert "construction" in regions[0].rationale.lower()


def test_change_typing_clearance():
    size = 64
    # Before: Forest
    before_ndvi = np.full((size, size), 0.80, dtype=np.float32)
    before_ndwi = np.full((size, size), -0.4, dtype=np.float32)
    before_ndbi = np.full((size, size), -0.3, dtype=np.float32)
    before_indices = SpectralIndices(before_ndvi, before_ndwi, before_ndbi, True, {})

    # After: Cleared ground (no concrete / built-up)
    after_ndvi = before_ndvi.copy()
    after_ndwi = before_ndwi.copy()
    after_ndbi = before_ndbi.copy()
    after_ndvi[15:35, 15:35] = 0.15  # NDVI dropped
    after_ndbi[15:35, 15:35] = -0.25 # NDBI stayed low
    after_indices = SpectralIndices(after_ndvi, after_ndwi, after_ndbi, True, {})

    change_mask = np.zeros((size, size), dtype=np.uint8)
    change_mask[15:35, 15:35] = 255

    regions = classify_change_regions(change_mask, before_indices, after_indices)
    assert len(regions) == 1
    assert regions[0].change_type == "clearance"


def test_change_typing_water_extent():
    size = 64
    # Before: Dry riverbed / flood zone
    before_ndvi = np.full((size, size), 0.1, dtype=np.float32)
    before_ndwi = np.full((size, size), -0.3, dtype=np.float32)
    before_ndbi = np.full((size, size), 0.0, dtype=np.float32)
    before_indices = SpectralIndices(before_ndvi, before_ndwi, before_ndbi, True, {})

    # After: Water expansion
    after_ndvi = before_ndvi.copy()
    after_ndwi = before_ndwi.copy()
    after_ndbi = before_ndbi.copy()
    after_ndwi[10:30, 10:45] = 0.65  # NDWI surged positive
    after_indices = SpectralIndices(after_ndvi, after_ndwi, after_ndbi, True, {})

    change_mask = np.zeros((size, size), dtype=np.uint8)
    change_mask[10:30, 10:45] = 255

    regions = classify_change_regions(change_mask, before_indices, after_indices)
    assert len(regions) == 1
    assert regions[0].change_type == "water_extent"


def test_change_typing_road_development():
    size = 100
    # Before: Open ground
    before_ndvi = np.full((size, size), 0.4, dtype=np.float32)
    before_ndwi = np.full((size, size), -0.4, dtype=np.float32)
    before_ndbi = np.full((size, size), -0.2, dtype=np.float32)
    before_indices = SpectralIndices(before_ndvi, before_ndwi, before_ndbi, True, {})

    # After: Long linear road strip (height=4, width=60) -> aspect ratio 15
    after_ndvi = before_ndvi.copy()
    after_ndwi = before_ndwi.copy()
    after_ndbi = before_ndbi.copy()
    after_ndvi[48:52, 20:80] = 0.05
    after_ndbi[48:52, 20:80] = 0.35
    after_indices = SpectralIndices(after_ndvi, after_ndwi, after_ndbi, True, {})

    change_mask = np.zeros((size, size), dtype=np.uint8)
    change_mask[48:52, 20:80] = 255

    regions = classify_change_regions(change_mask, before_indices, after_indices)
    assert len(regions) == 1
    assert regions[0].change_type == "road_development"
    assert regions[0].elongation > 2.5
