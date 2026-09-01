"""
Pure-array spatial co-registration module for satellite image pairs.

Aligns bi-temporal observations using OpenCV feature matching (ORB/SIFT)
and homography/affine warp correction before change detection diffing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import cv2
import numpy as np


@dataclass
class RegistrationResult:
    aligned_after: np.ndarray
    transform_matrix: Optional[np.ndarray]
    inliers: int
    correlation_before: float
    correlation_after: float
    is_aligned: bool
    dx: float = 0.0
    dy: float = 0.0


def _to_gray_uint8(img: np.ndarray) -> np.ndarray:
    """Convert float [0, 1] or uint8 [0, 255] (H, W) or (H, W, C) to uint8 (H, W)."""
    if img.ndim == 3:
        if img.shape[2] >= 3:
            # RGB -> Gray
            gray = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
        else:
            gray = img[..., 0]
    else:
        gray = img.copy()

    if gray.dtype != np.uint8:
        if gray.max() <= 1.0:
            gray = (gray * 255.0).clip(0, 255)
        gray = gray.astype(np.uint8)
    return gray


def compute_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Compute normalized cross-correlation between two grayscale arrays."""
    a_f = a.astype(np.float32)
    b_f = b.astype(np.float32)
    a_diff = a_f - a_f.mean()
    b_diff = b_f - b_f.mean()
    a_std = a_diff.std() + 1e-6
    b_std = b_diff.std() + 1e-6
    corr = float((a_diff * b_diff).mean() / (a_std * b_std))
    return max(-1.0, min(1.0, corr))


def register_image_pair(
    before_img: np.ndarray,
    after_img: np.ndarray,
    max_features: int = 1000,
    match_threshold: float = 0.75,
    min_inliers: int = 8,
) -> RegistrationResult:
    """
    Co-register `after_img` to `before_img`.
    
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
    gray_ref = _to_gray_uint8(before_img)
    gray_tgt = _to_gray_uint8(after_img)

    corr_before = compute_correlation(gray_ref, gray_tgt)

    # 1. Feature detection via ORB
    orb = cv2.ORB_create(nfeatures=max_features)
    kp1, des1 = orb.detectAndCompute(gray_ref, None)
    kp2, des2 = orb.detectAndCompute(gray_tgt, None)

    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        return RegistrationResult(
            aligned_after=after_img.copy(),
            transform_matrix=None,
            inliers=0,
            correlation_before=corr_before,
            correlation_after=corr_before,
            is_aligned=False,
        )

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
        return RegistrationResult(
            aligned_after=after_img.copy(),
            transform_matrix=None,
            inliers=len(good_matches),
            correlation_before=corr_before,
            correlation_after=corr_before,
            is_aligned=False,
        )

    src_pts = np.float32([kp2[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp1[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    # 3. Estimate affine or homography transformation
    matrix, mask = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    inliers = int(mask.sum()) if mask is not None else 0

    if matrix is None or inliers < min_inliers:
        return RegistrationResult(
            aligned_after=after_img.copy(),
            transform_matrix=None,
            inliers=inliers,
            correlation_before=corr_before,
            correlation_after=corr_before,
            is_aligned=False,
        )

    # Check that transform is reasonable (not degenerate scale/skew)
    dx = float(matrix[0, 2])
    dy = float(matrix[1, 2])
    scale_x = np.linalg.norm(matrix[0, :2])
    scale_y = np.linalg.norm(matrix[1, :2])

    if abs(scale_x - 1.0) > 0.25 or abs(scale_y - 1.0) > 0.25 or abs(dx) > (w * 0.4) or abs(dy) > (h * 0.4):
        # Degenerate warp rejected
        return RegistrationResult(
            aligned_after=after_img.copy(),
            transform_matrix=matrix,
            inliers=inliers,
            correlation_before=corr_before,
            correlation_after=corr_before,
            is_aligned=False,
            dx=dx,
            dy=dy,
        )

    # 4. Warp after_img to match before_img coordinates
    aligned_after = cv2.warpAffine(
        after_img,
        matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )

    gray_aligned = _to_gray_uint8(aligned_after)
    corr_after = compute_correlation(gray_ref, gray_aligned)

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
    )
