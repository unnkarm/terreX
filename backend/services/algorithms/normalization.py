"""
Pure-array relative radiometric normalization module.

Removes pseudo-change caused by solar illumination, atmosphere, sensor gain and
seasonal colour grading before any differencing happens.

Two strategies are provided:
  - `normalize_relative_radiometry` (preferred): a per-band gain/offset fitted
    on pseudo-invariant, cloud-free pixels. It corrects radiometry without
    normalising genuine ground change away.
  - `normalize_histogram_match`: full cumulative histogram matching, kept for
    cases where the two dates differ in more than gain and offset.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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


# ---------------------------------------------------------------------------
# Relative radiometric normalization via pseudo-invariant features (PIF)
# ---------------------------------------------------------------------------
@dataclass
class NormalizationResult:
    """Outcome of relative radiometric normalization, with its fitted transfer."""

    array: np.ndarray                # normalized source, same shape/dtype as input
    method: str                      # "pif-linear" | "histogram-match" | "identity"
    gains: List[float] = field(default_factory=list)
    offsets: List[float] = field(default_factory=list)
    pif_fraction: float = 0.0        # share of pixels used to fit the transfer
    shift_before: float = 0.0        # scene-mean |after - before| before normalization
    shift_after: float = 0.0         # …and after it
    detail: str = ""

    def summary(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "gains": [round(g, 5) for g in self.gains],
            "offsets": [round(o, 5) for o in self.offsets],
            "pif_fraction": round(float(self.pif_fraction), 4),
            "shift_before": round(float(self.shift_before), 5),
            "shift_after": round(float(self.shift_after), 5),
            "detail": self.detail,
        }


def _pseudo_invariant_mask(
    source: np.ndarray,
    reference: np.ndarray,
    valid_mask: Optional[np.ndarray],
    percentile: float,
) -> np.ndarray:
    """
    Pixels most likely to be unchanged between the two dates.

    Fitting the radiometric transfer on *all* pixels lets genuine change pull
    the gain/offset and partially normalise the change away. Restricting the
    fit to the quietest `percentile` of pixels — the classic pseudo-invariant
    feature approach — corrects illumination and sensor gain while leaving real
    ground change intact.
    """
    difference = np.abs(source.astype(np.float32) - reference.astype(np.float32))
    if difference.ndim == 3:
        difference = difference.mean(axis=-1)
    base = valid_mask.astype(bool) if valid_mask is not None else np.ones(difference.shape, dtype=bool)
    if not base.any():
        base = np.ones(difference.shape, dtype=bool)
    cutoff = float(np.percentile(difference[base], percentile))
    pif = base & (difference <= cutoff)
    return pif if pif.sum() >= 32 else base


def normalize_relative_radiometry(
    source: np.ndarray,
    reference: np.ndarray,
    valid_mask: Optional[np.ndarray] = None,
    pif_percentile: float = 70.0,
    gain_limits: Tuple[float, float] = (0.5, 2.0),
) -> NormalizationResult:
    """
    Normalize `source` onto `reference`'s radiometry with a per-band gain/offset
    fitted on pseudo-invariant, cloud-free pixels only.

    Each band gets `out = gain * src + offset`, where gain matches the robust
    spread (MAD) and offset matches the median of the invariant population.
    Falls back to cumulative histogram matching when a band's spread is
    degenerate, and to identity when the two rasters cannot be compared.
    """
    src = np.asarray(source, dtype=np.float32)
    ref = np.asarray(reference, dtype=np.float32)
    if src.ndim == 2:
        src = src[..., None]
    if ref.ndim == 2:
        ref = ref[..., None]

    if src.shape[:2] != ref.shape[:2]:
        return NormalizationResult(
            array=np.asarray(source),
            method="identity",
            detail="Source and reference grids differ — normalization skipped.",
        )

    shift_before = float(abs(src[..., : min(3, src.shape[-1])].mean() - ref[..., : min(3, ref.shape[-1])].mean()))
    pif = _pseudo_invariant_mask(
        src[..., : min(src.shape[-1], ref.shape[-1])],
        ref[..., : min(src.shape[-1], ref.shape[-1])],
        valid_mask,
        pif_percentile,
    )

    out = src.copy()
    gains: List[float] = []
    offsets: List[float] = []
    histogram_fallback = False

    for channel in range(min(src.shape[-1], ref.shape[-1])):
        s_vals = src[..., channel][pif]
        r_vals = ref[..., channel][pif]
        if s_vals.size == 0:
            gains.append(1.0)
            offsets.append(0.0)
            continue

        s_med = float(np.median(s_vals))
        r_med = float(np.median(r_vals))
        s_mad = float(np.median(np.abs(s_vals - s_med)))
        r_mad = float(np.median(np.abs(r_vals - r_med)))

        if s_mad < 1e-5 or r_mad < 1e-5:
            # Degenerate spread — a gain is meaningless, shift the median only.
            gain, offset = 1.0, r_med - s_med
            histogram_fallback = True
        else:
            gain = float(np.clip(r_mad / s_mad, gain_limits[0], gain_limits[1]))
            offset = r_med - gain * s_med

        out[..., channel] = np.clip(gain * src[..., channel] + offset, 0.0, 1.0)
        gains.append(gain)
        offsets.append(offset)

    shift_after = float(abs(out[..., : min(3, out.shape[-1])].mean() - ref[..., : min(3, ref.shape[-1])].mean()))
    detail = (
        f"Per-band gain/offset fitted on the quietest {pif_percentile:.0f}% of clear pixels "
        f"({float(pif.mean()) * 100:.1f}% of the tile); "
        f"scene-mean offset {shift_before:.4f} → {shift_after:.4f}."
    )
    if histogram_fallback:
        detail += " One or more bands had degenerate spread and were offset-only corrected."

    if np.asarray(source).ndim == 2:
        out = out[..., 0]

    return NormalizationResult(
        array=out.astype(np.float32),
        method="pif-linear",
        gains=gains,
        offsets=offsets,
        pif_fraction=float(pif.mean()),
        shift_before=shift_before,
        shift_after=shift_after,
        detail=detail,
    )
