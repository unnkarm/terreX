"""
Pure-NumPy image operators shared by the multi-evidence change pipeline.

Every helper here works on plain arrays with no OpenCV/SciPy requirement, so
the evidence layers behave identically whether or not the optional native
libraries are installed. Where OpenCV is available it is used for speed, but
the NumPy path is always the reference implementation.
"""
from __future__ import annotations

from typing import Optional, Tuple

try:
    import cv2
except ImportError:  # pragma: no cover - exercised on minimal installs
    cv2 = None
import numpy as np
from PIL import Image

EPS = 1e-8


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def resize_to(arr: np.ndarray, height: int, width: int) -> np.ndarray:
    """Bilinearly resample a 2D or 3D (H, W, C) array to (height, width)."""
    arr = np.asarray(arr, dtype=np.float32)
    if arr.shape[:2] == (height, width):
        return arr
    if cv2 is not None:
        resized = cv2.resize(arr, (width, height), interpolation=cv2.INTER_LINEAR)
        return resized.astype(np.float32, copy=False)
    if arr.ndim == 2:
        return np.asarray(
            Image.fromarray(arr).resize((width, height), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
    planes = [
        np.asarray(
            Image.fromarray(arr[..., c]).resize((width, height), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
        for c in range(arr.shape[-1])
    ]
    return np.stack(planes, axis=-1)


def to_gray(raster: np.ndarray) -> np.ndarray:
    """Collapse an (H, W) / (H, W, C) raster to a single float32 luminance plane."""
    arr = np.asarray(raster, dtype=np.float32)
    if arr.ndim == 2:
        return arr
    if arr.shape[-1] >= 3:
        return 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    return arr.mean(axis=-1)


# ---------------------------------------------------------------------------
# Local (windowed) statistics — integral-image based, O(H*W) regardless of radius
# ---------------------------------------------------------------------------
def _window_sum(arr: np.ndarray, radius: int) -> np.ndarray:
    """Sum over a (2*radius+1)^2 window, clipped at the image border."""
    arr = np.asarray(arr, dtype=np.float64)
    h, w = arr.shape
    integral = np.pad(arr.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
    rows = np.arange(h)
    cols = np.arange(w)
    y0 = np.clip(rows - radius, 0, h)
    y1 = np.clip(rows + radius + 1, 0, h)
    x0 = np.clip(cols - radius, 0, w)
    x1 = np.clip(cols + radius + 1, 0, w)
    return (
        integral[np.ix_(y1, x1)]
        - integral[np.ix_(y0, x1)]
        - integral[np.ix_(y1, x0)]
        + integral[np.ix_(y0, x0)]
    )


def box_mean(arr: np.ndarray, radius: int, mask: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Local mean over a (2*radius+1)^2 window.

    When `mask` is supplied the mean is taken over masked-in pixels only, so
    clouded / invalid neighbours never leak into a local statistic.
    """
    arr = np.asarray(arr, dtype=np.float32)
    if radius < 1:
        return arr.astype(np.float32, copy=False)
    if mask is None:
        counts = _window_sum(np.ones_like(arr, dtype=np.float64), radius)
        return (_window_sum(arr, radius) / np.maximum(counts, 1.0)).astype(np.float32)
    weights = mask.astype(np.float64)
    counts = _window_sum(weights, radius)
    totals = _window_sum(arr.astype(np.float64) * weights, radius)
    return (totals / np.maximum(counts, EPS)).astype(np.float32)


def local_structure_stats(
    a: np.ndarray,
    b: np.ndarray,
    radius: int,
    mask: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (mean_a, mean_b, var_a, var_b, covariance) over a local window."""
    mean_a = box_mean(a, radius, mask)
    mean_b = box_mean(b, radius, mask)
    var_a = np.maximum(box_mean(a * a, radius, mask) - mean_a * mean_a, 0.0)
    var_b = np.maximum(box_mean(b * b, radius, mask) - mean_b * mean_b, 0.0)
    cov = box_mean(a * b, radius, mask) - mean_a * mean_b
    return mean_a, mean_b, var_a, var_b, cov


def gradient_magnitude(gray: np.ndarray) -> np.ndarray:
    """Sobel-style gradient magnitude, normalised to roughly [0, 1]."""
    gray = np.asarray(gray, dtype=np.float32)
    gy, gx = np.gradient(gray)
    return np.sqrt(gx * gx + gy * gy).astype(np.float32)


# ---------------------------------------------------------------------------
# Binary morphology
# ---------------------------------------------------------------------------
def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Binary dilation by a square structuring element."""
    mask = np.asarray(mask, dtype=bool)
    if radius < 1 or not mask.any():
        return mask
    return _window_sum(mask.astype(np.float64), radius) > 0.5


def erode(mask: np.ndarray, radius: int) -> np.ndarray:
    """Binary erosion by a square structuring element."""
    mask = np.asarray(mask, dtype=bool)
    if radius < 1 or not mask.any():
        return mask
    counts = _window_sum(np.ones_like(mask, dtype=np.float64), radius)
    hits = _window_sum(mask.astype(np.float64), radius)
    return hits >= counts - 0.5


def morphological_open(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    """Erosion followed by dilation — removes isolated salt-noise detections."""
    if radius < 1:
        return np.asarray(mask, dtype=bool)
    return dilate(erode(mask, radius), radius)


def connected_labels(mask: np.ndarray) -> Tuple[np.ndarray, int]:
    """Label 8-connected components. Returns (labels, num_labels_including_background)."""
    binary = np.asarray(mask, dtype=np.uint8)
    if cv2 is not None:
        num_labels, labels = cv2.connectedComponents(binary, connectivity=8)
        return labels, num_labels
    try:
        from scipy.ndimage import label as _scipy_label

        labels, num = _scipy_label(binary, structure=np.ones((3, 3), dtype=np.uint8))
        return labels, int(num) + 1
    except ImportError:  # pragma: no cover - last-resort union-find
        return _label_numpy(binary)


def _label_numpy(binary: np.ndarray) -> Tuple[np.ndarray, int]:
    """Two-pass 8-connected labelling used when neither OpenCV nor SciPy exist."""
    h, w = binary.shape
    labels = np.zeros((h, w), dtype=np.int32)
    parent: list[int] = [0]

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    next_label = 1
    for y in range(h):
        for x in range(w):
            if not binary[y, x]:
                continue
            neighbours = []
            for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and labels[ny, nx]:
                    neighbours.append(int(labels[ny, nx]))
            if not neighbours:
                parent.append(next_label)
                labels[y, x] = next_label
                next_label += 1
            else:
                smallest = min(neighbours)
                labels[y, x] = smallest
                for other in neighbours:
                    union(smallest, other)

    remap: dict[int, int] = {}
    for y in range(h):
        for x in range(w):
            if labels[y, x]:
                root = find(int(labels[y, x]))
                labels[y, x] = remap.setdefault(root, len(remap) + 1)
    return labels, len(remap) + 1


def remove_small_regions(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    """Drop connected components smaller than `min_pixels`."""
    mask = np.asarray(mask, dtype=bool)
    if min_pixels <= 1 or not mask.any():
        return mask
    labels, num_labels = connected_labels(mask)
    if num_labels <= 1:
        return mask
    counts = np.bincount(labels.ravel(), minlength=num_labels)
    keep = counts >= min_pixels
    keep[0] = False
    return keep[labels]


# ---------------------------------------------------------------------------
# Robust statistics
# ---------------------------------------------------------------------------
def robust_center_scale(
    values: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> Tuple[float, float]:
    """
    Median and MAD-derived sigma of `values`, restricted to `mask` when given.

    MAD is used rather than mean/std because a genuine change region is, by
    construction, an outlier population that would inflate a plain standard
    deviation and hide itself.
    """
    arr = np.asarray(values, dtype=np.float32)
    sample = arr[mask] if mask is not None and np.any(mask) else arr.ravel()
    if sample.size == 0:
        return 0.0, 1.0
    median = float(np.median(sample))
    mad = float(np.median(np.abs(sample - median)))
    return median, max(1.4826 * mad, 1e-6)
