"""
Pure-array 2-layer change classification module.

Classifies detected change regions into the 4 PS-mandated classes:
1. Road development (Elongated / linear morphology + infrastructure signature)
2. Construction (Vegetation down + Built-up up / high SWIR & NDBI response)
3. Water-extent variation (NDWI shift + low SWIR / negative NDBI water response)
4. Clearance (Vegetation down without built-up or water response)
"""
from __future__ import annotations

from dataclasses import dataclass
try:
    import cv2
except ImportError:
    cv2 = None
import numpy as np

from services.algorithms.spectral import SpectralIndices, compute_spectral_deltas


@dataclass
class ChangeRegion:
    region_id: int
    change_type: str        # "construction" | "clearance" | "water_extent" | "road_development" | "unclassified"
    dynamics: str           # "appearance" | "disappearance" | "expansion" | "contraction"
    confidence: float
    area_pixels: int
    centroid: Tuple[float, float]  # (x, y)
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    mean_d_ndvi: float
    mean_d_ndwi: float
    mean_d_ndbi: float
    elongation: float
    rationale: str


def classify_change_regions(
    change_mask: np.ndarray,
    before_indices: SpectralIndices,
    after_indices: SpectralIndices,
    min_region_size: int = 6,
) -> List[ChangeRegion]:
    """
    Perform Layer-2 semantic classification on connected change regions.

    Args:
        change_mask: Binary boolean or uint8 mask (H, W) where True/255 indicates detected change.
        before_indices: Spectral indices for the 'before' observation.
        after_indices: Spectral indices for the 'after' observation.
        min_region_size: Minimum pixel area to consider a meaningful change region.

    Returns:
        List of ChangeRegion instances with classification and rationale.
    """
    binary_mask = (change_mask > 0).astype(np.uint8)
    if cv2 is not None:
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
    else:
        from scipy.ndimage import label
        labels, num_features = label(binary_mask)
        num_labels = num_features + 1
        stats, centroids = None, None

    deltas = compute_spectral_deltas(before_indices, after_indices)
    d_ndvi = deltas["d_ndvi"]
    d_ndwi = deltas["d_ndwi"]
    d_ndbi = deltas["d_ndbi"]

    results: List[ChangeRegion] = []

    for label_id in range(1, num_labels):
        region_mask = (labels == label_id)
        if stats is not None and cv2 is not None:
            area = int(stats[label_id, cv2.CC_STAT_AREA])
            if area < min_region_size:
                continue
            x = int(stats[label_id, cv2.CC_STAT_LEFT])
            y = int(stats[label_id, cv2.CC_STAT_TOP])
            w = int(stats[label_id, cv2.CC_STAT_WIDTH])
            h = int(stats[label_id, cv2.CC_STAT_HEIGHT])
            cx, cy = float(centroids[label_id][0]), float(centroids[label_id][1])
        else:
            area = int(region_mask.sum())
            if area < min_region_size:
                continue
            y_indices, x_indices = np.where(region_mask)
            if len(x_indices) == 0:
                continue
            x, y = int(x_indices.min()), int(y_indices.min())
            w, h = int(x_indices.max() - x + 1), int(y_indices.max() - y + 1)
            cx, cy = float(x_indices.mean()), float(y_indices.mean())

        mean_ndvi = float(d_ndvi[region_mask].mean())
        mean_ndwi = float(d_ndwi[region_mask].mean())
        mean_ndbi = float(d_ndbi[region_mask].mean())
        before_ndbi_mean = float(before_indices.ndbi[region_mask].mean())
        after_ndbi_mean = float(after_indices.ndbi[region_mask].mean())
        after_ndwi_mean = float(after_indices.ndwi[region_mask].mean())

        # Morphological analysis (elongation / aspect ratio)
        aspect = max(w / max(h, 1), h / max(w, 1))
        solidity = area / max(w * h, 1)

        # Region moments for rotational elongation
        region_pts = np.argwhere(region_mask)
        if len(region_pts) >= 6:
            cov = np.cov(region_pts, rowvar=False)
            eigenvals = np.linalg.eigvalsh(cov)
            eigenvals = np.sort(eigenvals)[::-1]
            elongation = float(np.sqrt(max(eigenvals[0], 1e-6) / max(eigenvals[1], 1e-6)))
        else:
            elongation = aspect

        # -------------------------------------------------------------------
        # 4-Class Classification Decision Logic + Multi-Temporal Dynamics
        # -------------------------------------------------------------------

        # 1. Road development: high linear elongation / aspect ratio + infrastructure/built signature
        if (elongation > 2.8 or (aspect > 3.0 and solidity < 0.6)) and (mean_ndbi > -0.15 or after_ndbi_mean > -0.10):
            change_type = "road_development"
            dynamics = "appearance" if elongation > 3.5 else "expansion"
            conf = min(0.95, 0.65 + 0.05 * min(elongation, 6.0))
            rationale = (
                f"High linear elongation ({elongation:.2f}) and spatial eccentricity "
                f"indicates linear infrastructure / road corridor {dynamics}."
            )

        # 2. Construction: strong built-up / SWIR increase, positive post-event NDBI
        elif (mean_ndbi > 0.15) or (after_ndbi_mean > 0.0 and mean_ndbi > 0.04):
            change_type = "construction"
            dynamics = "appearance" if before_ndbi_mean < -0.05 else "expansion"
            conf = min(0.95, 0.65 + 0.4 * max(mean_ndbi, 0.0) + 0.3 * max(-mean_ndvi, 0.0))
            rationale = (
                f"Built-up index increase (dNDBI={mean_ndbi:+.2f}, post-event NDBI={after_ndbi_mean:+.2f}) "
                f"with vegetation loss (dNDVI={mean_ndvi:+.2f}) indicates structural construction / built {dynamics}."
            )

        # 3. Water-extent variation: strong shift in water index + water spectral signature (low SWIR/NDBI)
        elif (abs(mean_ndwi) > 0.15 or after_ndwi_mean > 0.10) and (after_ndbi_mean <= 0.0 or mean_ndbi <= 0.0):
            change_type = "water_extent"
            dynamics = "expansion" if mean_ndwi > 0 else "contraction"
            direction = "expansion" if mean_ndwi > 0 else "contraction/recession"
            conf = min(0.95, 0.70 + abs(mean_ndwi))
            rationale = (
                f"Significant NDWI shift ({mean_ndwi:+.2f}) matches water body {direction}."
            )

        # 4. Clearance: vegetation loss without high built-up signature
        elif mean_ndvi < -0.08:
            change_type = "clearance"
            dynamics = "disappearance" if mean_ndvi < -0.15 else "expansion"
            conf = min(0.90, 0.60 + 0.5 * abs(mean_ndvi))
            rationale = (
                f"Vegetation reduction (dNDVI={mean_ndvi:+.2f}) without structural built-up response "
                f"(post-event NDBI={after_ndbi_mean:+.2f}) indicates land clearance or vegetation {dynamics}."
            )

        # 5. Default / unclassified
        else:
            change_type = "unclassified"
            dynamics = "expansion" if mean_ndbi > 0 else "contraction"
            conf = 0.50
            rationale = f"General ground spectral shift (dNDVI={mean_ndvi:+.2f}, dNDBI={mean_ndbi:+.2f})."

        results.append(
            ChangeRegion(
                region_id=label_id,
                change_type=change_type,
                dynamics=dynamics,
                confidence=round(conf, 3),
                area_pixels=area,
                centroid=(round(cx, 2), round(cy, 2)),
                bbox=(x, y, w, h),
                mean_d_ndvi=round(mean_ndvi, 4),
                mean_d_ndwi=round(mean_ndwi, 4),
                mean_d_ndbi=round(mean_ndbi, 4),
                elongation=round(elongation, 2),
                rationale=rationale,
            )
        )

    return results
