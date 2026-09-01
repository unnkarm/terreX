"""
Pure-array multispectral and RGB spectral index computation module.

Computes:
- NDVI (Normalized Difference Vegetation Index) / RGB VARI fallback
- NDWI (Normalized Difference Water Index) / RGB Water proxy fallback
- NDBI (Normalized Difference Built-up Index) / RGB Built-up proxy fallback
- Spectral deltas between bi-temporal observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import numpy as np


@dataclass
class SpectralIndices:
    ndvi: np.ndarray        # [-1, 1] Vegetation index
    ndwi: np.ndarray        # [-1, 1] Water index
    ndbi: np.ndarray        # [-1, 1] Built-up index
    is_multispectral: bool  # True if calculated with true NIR/SWIR bands
    source_bands: Dict[str, int]


def _safe_ratio(numerator: np.ndarray, denominator: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Safe normalized difference ratio (A - B) / (A + B + eps)."""
    denom = np.where(np.abs(denominator) < eps, eps, denominator)
    ratio = numerator / denom
    return np.clip(ratio, -1.0, 1.0)


def compute_spectral_indices(
    raster: np.ndarray,
    band_map: Optional[Dict[str, int]] = None,
) -> SpectralIndices:
    """
    Compute NDVI, NDWI, and NDBI from a raster (H, W, C) or (C, H, W).
    
    Args:
        raster: Multi-band image array.
        band_map: Dictionary mapping band names ('blue', 'green', 'red', 'nir', 'swir1')
                  to channel index (0-based). If None, defaults to standard RGB/multi channel order.

    Returns:
        SpectralIndices dataclass.
    """
    arr = raster.astype(np.float32)
    # Ensure (H, W, C)
    if arr.ndim == 3 and arr.shape[0] <= 16 and arr.shape[0] < arr.shape[1] and arr.shape[0] < arr.shape[2]:
        arr = np.transpose(arr, (1, 2, 0))

    if arr.max() > 1.0:
        arr = arr / (255.0 if arr.max() <= 255.0 else 10000.0)

    h, w, c = arr.shape
    if band_map is None:
        if c >= 5:
            # Assumed Sentinel-2 standard stack [B, G, R, NIR, SWIR1]
            band_map = {"blue": 0, "green": 1, "red": 2, "nir": 3, "swir1": 4}
        elif c >= 4:
            # Assumed 4-band [B, G, R, NIR]
            band_map = {"blue": 0, "green": 1, "red": 2, "nir": 3}
        else:
            # Standard 3-band RGB [R, G, B] or [B, G, R]
            band_map = {"red": 0, "green": 1, "blue": 2}

    has_nir = "nir" in band_map and band_map["nir"] < c
    has_swir = "swir1" in band_map and band_map["swir1"] < c
    has_red = "red" in band_map and band_map["red"] < c
    has_green = "green" in band_map and band_map["green"] < c
    has_blue = "blue" in band_map and band_map["blue"] < c

    red = arr[..., band_map["red"]] if has_red else np.zeros((h, w), dtype=np.float32)
    green = arr[..., band_map["green"]] if has_green else np.zeros((h, w), dtype=np.float32)
    blue = arr[..., band_map["blue"]] if has_blue else np.zeros((h, w), dtype=np.float32)

    if has_nir and has_red:
        nir = arr[..., band_map["nir"]]
        # Standard NDVI = (NIR - Red) / (NIR + Red)
        ndvi = _safe_ratio(nir - red, nir + red)
        # McFeeters NDWI = (Green - NIR) / (Green + NIR)
        ndwi = _safe_ratio(green - nir, green + nir)
        if has_swir:
            swir1 = arr[..., band_map["swir1"]]
            # NDBI = (SWIR1 - NIR) / (SWIR1 + NIR)
            ndbi = _safe_ratio(swir1 - nir, swir1 + nir)
        else:
            # Urban index proxy using (Red - NIR)
            ndbi = _safe_ratio(red - nir, red + nir)
        is_multispectral = True
    else:
        # RGB Fallbacks
        # VARI (Visible Atmospherically Resistant Index) = (Green - Red) / (Green + Red - Blue)
        ndvi = _safe_ratio(green - red, green + red - blue)
        # RGB Water Proxy: Blue-Green dominance over Red
        ndwi = _safe_ratio(blue - red, blue + red)
        # RGB Built-up Proxy: Brightness + Red/Green balance
        brightness = (red + green + blue) / 3.0
        ndbi = _safe_ratio(red - green, red + green) * 0.5 + (brightness - 0.5)
        is_multispectral = False

    return SpectralIndices(
        ndvi=ndvi,
        ndwi=ndwi,
        ndbi=ndbi,
        is_multispectral=is_multispectral,
        source_bands=band_map,
    )


def compute_spectral_deltas(
    before_indices: SpectralIndices,
    after_indices: SpectralIndices,
) -> Dict[str, np.ndarray]:
    """
    Compute delta maps: after - before for NDVI, NDWI, NDBI.
    Positive delta means increase; negative means decrease.
    """
    return {
        "d_ndvi": after_indices.ndvi - before_indices.ndvi,
        "d_ndwi": after_indices.ndwi - before_indices.ndwi,
        "d_ndbi": after_indices.ndbi - before_indices.ndbi,
    }
