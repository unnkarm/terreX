"""
Pure-array relative radiometric normalization module.

Applies histogram matching between multi-temporal observation pairs to minimize
pseudo-change caused by solar illumination, atmosphere, and seasonal color grading.
"""
from __future__ import annotations

from typing import Optional
import numpy as np


def _match_channel_histogram(
    source_channel: np.ndarray,
    reference_channel: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Match the cumulative distribution function (CDF) of source_channel to reference_channel.
    source_channel and reference_channel: 2D float32 [0, 1] or uint8 [0, 255].
    mask: boolean 2D array, True where pixels are valid (unmasked).
    """
    is_float = np.issubdtype(source_channel.dtype, np.floating)
    src = source_channel if not is_float else (source_channel * 255.0).clip(0, 255).astype(np.uint8)
    ref = reference_channel if not np.issubdtype(reference_channel.dtype, np.floating) else (reference_channel * 255.0).clip(0, 255).astype(np.uint8)

    if mask is not None:
        src_valid = src[mask]
        ref_valid = ref[mask]
    else:
        src_valid = src.ravel()
        ref_valid = ref.ravel()

    if len(src_valid) == 0 or len(ref_valid) == 0:
        return source_channel.copy()

    # Calculate empirical CDFs
    src_counts = np.bincount(src_valid, minlength=256)
    ref_counts = np.bincount(ref_valid, minlength=256)

    src_cdf = src_counts.cumsum().astype(np.float64)
    src_cdf /= src_cdf[-1] if src_cdf[-1] > 0 else 1.0

    ref_cdf = ref_counts.cumsum().astype(np.float64)
    ref_cdf /= ref_cdf[-1] if ref_cdf[-1] > 0 else 1.0

    # Create mapping table: for each value in src, find closest value in ref CDF
    lookup_table = np.zeros(256, dtype=np.uint8)
    for src_val in range(256):
        closest_ref_val = np.argmin(np.abs(ref_cdf - src_cdf[src_val]))
        lookup_table[src_val] = closest_ref_val

    matched = lookup_table[src]
    if is_float:
        return (matched.astype(np.float32) / 255.0).clip(0.0, 1.0)
    return matched


def normalize_histogram_match(
    source: np.ndarray,
    reference: np.ndarray,
    valid_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Radiometrically normalize `source` to match `reference` distribution.

    Args:
        source: Image array (H, W) or (H, W, C).
        reference: Reference image array (H, W) or (H, W, C).
        valid_mask: Optional boolean mask (H, W), True for clear/valid ground pixels.

    Returns:
        Normalized image array with same shape and dtype as `source`.
    """
    if source.ndim == 2:
        ref_ch = reference if reference.ndim == 2 else reference[..., 0]
        return _match_channel_histogram(source, ref_ch, mask=valid_mask)

    out = np.zeros_like(source)
    num_channels = min(source.shape[-1], reference.shape[-1])
    for c in range(num_channels):
        out[..., c] = _match_channel_histogram(
            source[..., c],
            reference[..., c],
            mask=valid_mask,
        )
    # If source has extra channels (e.g. NIR/SWIR), copy remaining as-is or match against channel 0
    if source.shape[-1] > num_channels:
        out[..., num_channels:] = source[..., num_channels:]

    return out
