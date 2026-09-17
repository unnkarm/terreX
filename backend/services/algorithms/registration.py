"""
Pure-array spatial co-registration module for satellite image pairs.

Aligns bi-temporal observations using OpenCV feature matching (ORB/SIFT)
and homography/affine warp correction before change detection diffing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    import cv2
except ImportError:
    cv2 = None
import numpy as np


@dataclass
class RegistrationResult:
    aligned_after: np.ndarray
    transform_matrix: Optional[np.ndarray]
    inliers: int
    correlation_before: float
    correlation_after: float
    is_aligned: bool
    # Translation the warp applied, in pixels.
    dx: float = 0.0
    dy: float = 0.0
    # Misalignment still measurable *after* the warp — this, not the applied
    # correction, is what downstream suppression must react to.
    residual_dx: float = 0.0
    residual_dy: float = 0.0
    # How alignment was achieved: "orb-affine" | "fft-phase-correlation" | "none".
    method: str = "none"
    # Pixels of `aligned_after` that came from real source data rather than
    # border fill introduced by the warp. Downstream masking excludes the rest.
    footprint: Optional[np.ndarray] = None

    @property
    def residual_shift_px(self) -> float:
        """Magnitude of the misalignment remaining after co-registration."""
        return float((self.residual_dx ** 2 + self.residual_dy ** 2) ** 0.5)


def warp_footprint(transform_matrix, height: int, width: int) -> Optional[np.ndarray]:
    """
    Boolean mask of destination pixels backed by real source data.

    Warping with BORDER_REFLECT_101 invents plausible-looking pixels along the
    edge; comparing against them manufactures change, so they are masked out.
    """
    if transform_matrix is None or cv2 is None:
        return None
    ones = np.ones((height, width), dtype=np.float32)
    warped = cv2.warpAffine(
        ones,
        transform_matrix,
        (width, height),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0.0,
    )
    return warped > 0.999


def apply_transform(
    plane: np.ndarray,
    transform_matrix,
    height: int,
    width: int,
    nearest: bool = True,
) -> np.ndarray:
    """
    Re-apply a registration warp to an ancillary plane (quality mask, scene
    classification, …) so it stays pixel-aligned with the warped imagery.
    Categorical planes must use nearest-neighbour so class codes survive.
    """
    if transform_matrix is None or cv2 is None:
        return plane
    original_dtype = np.asarray(plane).dtype
    warped = cv2.warpAffine(
        np.asarray(plane, dtype=np.float32),
        transform_matrix,
        (width, height),
        flags=cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0.0,
    )
    return warped.astype(original_dtype, copy=False)


def _to_gray_uint8(img: np.ndarray, stretch: bool = True) -> np.ndarray:
    """
    Convert float [0, 1] or uint8 [0, 255] (H, W) or (H, W, C) to uint8 (H, W).

    ORB and phase correlation both need 8-bit input, and a naive cast throws
    away dark, low-contrast scenes: forest and water tiles occupy only a few
    grey levels, leaving the matcher nothing to lock onto. A 2nd-98th
    percentile stretch restores that detail before quantisation. The stretch is
    monotonic, so it changes neither the geometry being estimated nor the
    normalised correlation computed from the result.
    """
    if img.ndim == 3:
        if img.shape[2] >= 3:
            # RGB -> Gray
            gray = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
        else:
            gray = img[..., 0]
    else:
        gray = img.copy()

    if gray.dtype == np.uint8:
        return gray

    gray = np.asarray(gray, dtype=np.float32)
    if stretch:
        finite = gray[np.isfinite(gray)]
        if finite.size:
            low, high = np.percentile(finite, (2.0, 98.0))
            if high - low > 1e-6:
                gray = (gray - low) / (high - low)
    elif gray.max() <= 1.0:
        pass
    return (np.clip(gray, 0.0, 1.0) * 255.0).astype(np.uint8)


def _to_gray_float(img: np.ndarray) -> np.ndarray:
    """
    Luminance as float, with no quantisation.

    Correlation must be measured on the real values: rounding a low-contrast
    tile to 8 bits first can collapse its dynamic range to a handful of grey
    levels and report two near-identical images as uncorrelated.
    """
    arr = np.asarray(img, dtype=np.float32)
    if arr.ndim == 3:
        return (
            0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
            if arr.shape[2] >= 3
            else arr[..., 0]
        )
    return arr


def compute_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Compute normalized cross-correlation between two grayscale arrays."""
    a_f = np.asarray(a, dtype=np.float32)
    b_f = np.asarray(b, dtype=np.float32)
    a_diff = a_f - a_f.mean()
    b_diff = b_f - b_f.mean()
    a_std = a_diff.std() + 1e-6
    b_std = b_diff.std() + 1e-6
    corr = float((a_diff * b_diff).mean() / (a_std * b_std))
    return max(-1.0, min(1.0, corr))


def measure_residual_shift(reference: np.ndarray, aligned: np.ndarray) -> tuple:
    """
    Misalignment still present after warping, via FFT phase correlation.

    The translation a warp *applied* says nothing about how well the result
    lines up — that is what was corrected. Downstream stages need the shift
    that remains, so it is measured directly on the warped output.
    """
    if cv2 is None:
        return 0.0, 0.0
    try:
        (res_dx, res_dy), _ = cv2.phaseCorrelate(
            _to_gray_uint8(reference).astype(np.float64),
            _to_gray_uint8(aligned).astype(np.float64),
        )
        return float(res_dx), float(res_dy)
    except cv2.error:
        return 0.0, 0.0


def _warp(image: np.ndarray, matrix: np.ndarray, height: int, width: int) -> np.ndarray:
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )


def _phase_correlation_fallback(
    before_img: np.ndarray,
    after_img: np.ndarray,
    gray_ref: np.ndarray,
    gray_tgt: np.ndarray,
    corr_before: float,
    inliers: int,
) -> Optional[RegistrationResult]:
    """
    Sub-pixel FFT phase-correlation alignment, used when feature matching does
    not find enough reliable correspondences (low-texture scenes, heavy cloud,
    dissimilar seasons).

    Returns None when the estimated shift is implausibly large, in which case
    the caller reports the pair as unaligned rather than warping it blindly.
    """
    h, w = before_img.shape[:2]
    # phaseCorrelate(a, b) reports how far b sits from a. Bringing b back onto
    # a therefore means translating by the negative of that offset — applying
    # it as-is doubles the misalignment instead of removing it.
    (offset_dx, offset_dy), _response = cv2.phaseCorrelate(
        gray_ref.astype(np.float64), gray_tgt.astype(np.float64)
    )
    if abs(offset_dx) >= (w * 0.25) or abs(offset_dy) >= (h * 0.25):
        return None

    shift_dx, shift_dy = -offset_dx, -offset_dy
    matrix = np.float32([[1.0, 0.0, shift_dx], [0.0, 1.0, shift_dy]])
    aligned_after = _warp(after_img, matrix, h, w)
    corr_after = compute_correlation(_to_gray_float(before_img), _to_gray_float(aligned_after))
    residual_dx, residual_dy = measure_residual_shift(before_img, aligned_after)

    return RegistrationResult(
        aligned_after=aligned_after,
        transform_matrix=matrix,
        inliers=inliers,
        correlation_before=corr_before,
        correlation_after=corr_after,
        # Correlation between two dates drops with genuine ground change as well
        # as with misalignment, so alignment is judged on whether the warp held
        # or improved it, against an absolute floor that pure noise cannot meet.
        is_aligned=corr_after >= max(0.3, corr_before - 0.05),
        dx=float(shift_dx),
        dy=float(shift_dy),
        residual_dx=residual_dx,
        residual_dy=residual_dy,
        method="fft-phase-correlation",
        footprint=warp_footprint(matrix, h, w),
    )


def _unaligned(
    after_img: np.ndarray,
    matrix,
    inliers: int,
    corr_before: float,
    dx: float = 0.0,
    dy: float = 0.0,
) -> RegistrationResult:
    """The pair could not be co-registered; it is returned untouched and flagged."""
    return RegistrationResult(
        aligned_after=after_img.copy(),
        transform_matrix=matrix,
        inliers=inliers,
        correlation_before=corr_before,
        correlation_after=corr_before,
        is_aligned=False,
        dx=dx,
        dy=dy,
        # Nothing was corrected, so whatever misalignment exists is still there.
        residual_dx=dx,
        residual_dy=dy,
        method="none",
    )


def register_image_pair(
    before_img: np.ndarray,
    after_img: np.ndarray,
    max_features: int = 1000,
    match_threshold: float = 0.75,
    min_inliers: int = 8,
) -> RegistrationResult:
    """
    Co-register `after_img` to `before_img`.

    Tries ORB feature matching with a RANSAC-fitted partial affine transform
    first, falling back to sub-pixel FFT phase correlation. Every returned
    correlation is measured on the actual imagery — a pair that could not be
    aligned reports that honestly rather than a flattering default, because the
    evidence-fusion and suppression stages downstream key off these numbers.

    Args:
        before_img: Reference image (H, W) or (H, W, C).
        after_img: Target image to align (H, W) or (H, W, C).
        max_features: Max keypoints for ORB detector.
        match_threshold: Lowe's ratio test threshold.
        min_inliers: Minimum RANSAC inliers to accept transform.

    Returns:
        RegistrationResult containing aligned after_img and diagnostics.
    """
    h, w = before_img.shape[:2]
    # 8-bit, contrast-stretched views for OpenCV; float luminance for every
    # correlation measurement.
    gray_ref = _to_gray_uint8(before_img)
    gray_tgt = _to_gray_uint8(after_img)
    float_ref = _to_gray_float(before_img)

    corr_before = compute_correlation(float_ref, _to_gray_float(after_img))
    if cv2 is None:
        # Without OpenCV no warp is possible; report the pair as it stands so
        # the caller can decide, rather than claiming an alignment that never ran.
        return RegistrationResult(
            aligned_after=after_img.copy(),
            transform_matrix=None,
            inliers=0,
            correlation_before=corr_before,
            correlation_after=corr_before,
            is_aligned=corr_before >= 0.9,
            method="none",
        )

    # 1. Feature detection via ORB
    orb = cv2.ORB_create(nfeatures=max_features)
    kp1, des1 = orb.detectAndCompute(gray_ref, None)
    kp2, des2 = orb.detectAndCompute(gray_tgt, None)

    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        fallback = _phase_correlation_fallback(before_img, after_img, gray_ref, gray_tgt, corr_before, 0)
        return fallback if fallback is not None else _unaligned(after_img, None, 0, corr_before)

    # 2. Match descriptors with BFMatcher (Hamming distance for ORB)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(des2, des1, k=2)

    # Ratio test
    good_matches = []
    for m_pair in matches:
        if len(m_pair) == 2:
            m, n = m_pair
            if m.distance < match_threshold * n.distance:
                good_matches.append(m)

    if len(good_matches) < min_inliers:
        fallback = _phase_correlation_fallback(
            before_img, after_img, gray_ref, gray_tgt, corr_before, len(good_matches)
        )
        return fallback if fallback is not None else _unaligned(after_img, None, len(good_matches), corr_before)

    src_pts = np.float32([kp2[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp1[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    # 3. Estimate affine or homography transformation
    matrix, mask = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    inliers = int(mask.sum()) if mask is not None else 0

    if matrix is None or inliers < min_inliers:
        fallback = _phase_correlation_fallback(before_img, after_img, gray_ref, gray_tgt, corr_before, inliers)
        return fallback if fallback is not None else _unaligned(after_img, None, inliers, corr_before)

    # Check that transform is reasonable (not degenerate scale/skew)
    dx = float(matrix[0, 2])
    dy = float(matrix[1, 2])
    scale_x = np.linalg.norm(matrix[0, :2])
    scale_y = np.linalg.norm(matrix[1, :2])

    if abs(scale_x - 1.0) > 0.25 or abs(scale_y - 1.0) > 0.25 or abs(dx) > (w * 0.4) or abs(dy) > (h * 0.4):
        # Degenerate warp rejected
        return _unaligned(after_img, matrix, inliers, corr_before, dx, dy)

    # 4. Warp after_img to match before_img coordinates
    aligned_after = _warp(after_img, matrix, h, w)
    corr_after = compute_correlation(float_ref, _to_gray_float(aligned_after))
    residual_dx, residual_dy = measure_residual_shift(before_img, aligned_after)

    # Check if alignment improved correlation or retained high correlation
    is_aligned = (corr_after >= corr_before - 0.05) and (inliers >= min_inliers)

    return RegistrationResult(
        aligned_after=aligned_after,
        transform_matrix=matrix,
        inliers=inliers,
        correlation_before=corr_before,
        correlation_after=corr_after,
        is_aligned=is_aligned,
        dx=dx,
        dy=dy,
        residual_dx=residual_dx,
        residual_dy=residual_dy,
        method="orb-affine",
        footprint=warp_footprint(matrix, h, w),
    )
