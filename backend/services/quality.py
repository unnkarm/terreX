"""
Image-quality checks shared by ingestion (Feature 1) and false-alarm
suppression (Feature 5).

These are simple, explainable heuristics rather than a trained model —
appropriate for an MVP and easy to reason about in a demo.
"""
from __future__ import annotations

import numpy as np


def cloud_fraction_estimate(rgb: np.ndarray) -> float:
    """
    Very simple cloud/haze heuristic: clouds/haze tend to be bright AND
    low-saturation (all bands close together). Returns fraction in [0,1].
    Expects rgb as (H, W, 3) float in [0, 1].
    """
    maxc = rgb.max(axis=-1)
    minc = rgb.min(axis=-1)
    brightness = rgb.mean(axis=-1)
    saturation = (maxc - minc) / (maxc + 1e-6)
    cloud_like = (brightness > 0.75) & (saturation < 0.15)
    return float(cloud_like.mean())


def valid_pixel_fraction(raster: np.ndarray, nodata_value=None) -> float:
    """Fraction of pixels that are not nodata / not all-zero across bands."""
    if nodata_value is not None:
        valid = ~np.all(raster == nodata_value, axis=0)
    else:
        valid = ~np.all(raster == 0, axis=0)
    return float(valid.mean())


def sharpness_score(gray: np.ndarray) -> float:
    """Laplacian-variance style sharpness proxy, normalised to ~[0,1]."""
    gy, gx = np.gradient(gray)
    lap = np.gradient(gx, axis=1) + np.gradient(gy, axis=0)
    var = float(np.var(lap))
    return float(min(var / 0.02, 1.0))


def overall_quality_score(cloud_frac: float, valid_frac: float, sharpness: float) -> float:
    """Combine into a single 0..1 quality score (simple weighted product)."""
    cloud_term = 1.0 - cloud_frac
    score = 0.45 * cloud_term + 0.35 * valid_frac + 0.20 * sharpness
    return float(np.clip(score, 0.0, 1.0))


def registration_offset_estimate(before_gray: np.ndarray, after_gray: np.ndarray, max_shift: int = 8) -> tuple:
    """
    Estimate misregistration between two co-located patches via simple
    normalized cross-correlation search over small pixel shifts. Returns
    (dx, dy, best_correlation). Large residual shift => poor registration,
    used to suppress false "change" caused by misalignment rather than a
    real change model failure.
    """
    best = (0, 0, -1.0)
    a = before_gray - before_gray.mean()
    a_std = a.std() + 1e-6
    h, w = after_gray.shape
    for dy in range(-max_shift, max_shift + 1, 2):
        for dx in range(-max_shift, max_shift + 1, 2):
            shifted = np.roll(np.roll(after_gray, dy, axis=0), dx, axis=1)
            b = shifted - shifted.mean()
            b_std = b.std() + 1e-6
            corr = float((a * b).mean() / (a_std * b_std))
            if corr > best[2]:
                best = (dx, dy, corr)
    return best
