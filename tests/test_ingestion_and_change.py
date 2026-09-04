"""
Integration test for windowed multispectral ingestion and change analysis pipeline.
"""
import sys
from pathlib import Path

# Add backend to path for tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import rasterio
import numpy as np
import pytest

from services.ingestion import _resolve_band_map, _read_tile_rgb_float, _compute_tile_bounds_wgs84
from services.algorithms.spectral import compute_spectral_indices, compute_spectral_deltas
from services.algorithms.change_classifier import classify_change_regions
from services.change_detection import (
    _difference_to_change_map,
    _extract_pair_features,
    _prepare_prithvi_input,
)


def test_windowed_multispectral_sample_scenes():
    incoming_dir = Path(__file__).resolve().parent.parent / "data" / "incoming"
    scene_files = sorted(list(incoming_dir.glob("*.tif")))
    if not scene_files:
        pytest.skip("No local sample scenes found")

    # Verify first scene properties
    with rasterio.open(scene_files[0]) as ds1:
        assert ds1.count >= 6
        assert ds1.width >= 64
        assert ds1.height >= 64
        assert ds1.crs is not None

        bmap = _resolve_band_map(ds1, "Sentinel-2")
        assert "red" in bmap and "nir" in bmap and "swir1" in bmap

        # Test windowed reading (256x256 window)
        win = rasterio.windows.Window(0, 0, 256, 256)
        rgb_patch = _read_tile_rgb_float(ds1, win, bmap)
        assert rgb_patch.shape == (256, 256, 3)
        assert rgb_patch.min() >= 0.0 and rgb_patch.max() <= 1.0

        # Test coordinate calculation
        min_lon, min_lat, max_lon, max_lat, c_lon, c_lat = _compute_tile_bounds_wgs84(
            ds1, 0, 0, 256, 256
        )
        assert min_lon < max_lon
        assert min_lat < max_lat
        assert min_lon <= c_lon <= max_lon
        assert min_lat <= c_lat <= max_lat


def test_multispectral_change_between_dates():
    incoming_dir = Path(__file__).resolve().parent.parent / "data" / "incoming"
    # Compare 20230101 (before settlement grew) and 20240101 (after settlement & road grew)
    f_before = incoming_dir / "Sentinel-2_20230101_demoAOI.tif"
    f_after = incoming_dir / "Sentinel-2_20240101_demoAOI.tif"

    if not f_before.exists() or not f_after.exists():
        pytest.skip("Synthetic scenes not found")

    with rasterio.open(f_before) as ds_b, rasterio.open(f_after) as ds_a:
        bmap_b = _resolve_band_map(ds_b, "Sentinel-2")
        bmap_a = _resolve_band_map(ds_a, "Sentinel-2")

        arr_b = ds_b.read().astype(np.float32)  # (6, H, W)
        arr_a = ds_a.read().astype(np.float32)

        indices_b = compute_spectral_indices(arr_b, {k: v - 1 for k, v in bmap_b.items()})
        indices_a = compute_spectral_indices(arr_a, {k: v - 1 for k, v in bmap_a.items()})

        deltas = compute_spectral_deltas(indices_b, indices_a)
        
        # In settlement/road area, NDBI should have increased and NDVI decreased
        d_ndbi = deltas["d_ndbi"]
        d_ndvi = deltas["d_ndvi"]

        # Synthetic change mask (where NDBI increased or NDVI dropped)
        diff_mask = ((d_ndbi > 0.05) | (d_ndvi < -0.10)).astype(np.uint8)
        regions = classify_change_regions(diff_mask, indices_b, indices_a, min_region_size=20)

        assert len(regions) >= 1
        found_types = {r.change_type for r in regions}
        # Either construction, road_development, or both must be present in the growing settlement
        assert ("construction" in found_types) or ("road_development" in found_types)


def test_prithvi_input_requires_six_ordered_bands():
    raster = np.zeros((4, 4, 7), dtype=np.float32)
    for channel in range(raster.shape[-1]):
        raster[..., channel] = channel

    prepared = _prepare_prithvi_input(
        raster,
        {"blue": 0, "green": 1, "red": 2, "nir": 3, "swir1": 4, "swir2": 5, "scl": 6},
    )

    assert prepared.shape == (6, 4, 4)
    assert prepared[:, 0, 0].tolist() == [0, 1, 2, 3, 4, 5]
    assert _prepare_prithvi_input(raster, {"blue": 0, "green": 1, "red": 2}) is None


def test_pair_features_fallback_together_for_ambiguous_side(monkeypatch):
    import services.change_detection as change_detection

    class FakePrithvi:
        def extract(self, image_chw):
            from services.prithvi import FeatureMap

            return FeatureMap(image_chw.mean(axis=0, keepdims=False)[..., None], "fake", image_chw.shape[0] != 6)

    monkeypatch.setattr(change_detection, "prithvi_service", FakePrithvi())
    before = np.ones((16, 16, 6), dtype=np.float32)
    after = np.ones((16, 16, 3), dtype=np.float32)

    before_feat, before_chw, after_feat, after_chw = _extract_pair_features(
        before,
        {"blue": 0, "green": 1, "red": 2, "nir": 3, "swir1": 4, "swir2": 5},
        after,
        {"blue": 0, "green": 1, "red": 2},
    )

    assert before_chw.shape[0] == after_chw.shape[0] == 3
    assert before_feat.is_placeholder is True
    assert after_feat.is_placeholder is True


def test_difference_to_change_map_rejects_mixed_feature_shapes():
    with pytest.raises(ValueError, match="feature shapes do not match"):
        _difference_to_change_map(
            np.zeros((2, 2, 768), dtype=np.float32),
            np.zeros((2, 2, 7), dtype=np.float32),
        )
