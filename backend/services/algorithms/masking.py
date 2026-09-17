"""
Cloud / shadow / validity masking — stage 3 of the change pipeline.

Change evidence must never be computed over pixels the sensor could not see.
This module produces a per-pixel usable mask for a single observation, with an
explicit breakdown of *why* each pixel was rejected so the analyst-facing
evidence panel can attribute suppressed area to a named cause.

Two paths:
  - Scene classification (SCL) when a Sentinel-2 L2A classification plane is
    available. This is authoritative and preferred.
  - A transparent brightness / whiteness / NIR heuristic otherwise, matching
    the ingestion-time heuristic in services.quality so a tile's mask means
    the same thing at ingest and at analysis time.

Cloud and shadow masks are dilated by a few pixels because both bleed into
their neighbourhood (semi-transparent cloud edge, penumbra) and those halo
pixels are the classic source of ring-shaped false change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from services.algorithms.imageops import dilate

# Sentinel-2 L2A scene-classification codes.
SCL_NODATA = (0,)
SCL_SATURATED = (1,)
SCL_SHADOW = (2, 3)          # dark area / cloud shadow
SCL_CLOUD = (8, 9, 10)       # cloud medium prob / high prob / thin cirrus
SCL_SNOW = (11,)

# Heuristic thresholds on [0, 1] reflectance.
#
# Cloud is tested absolutely: a cloud really is bright, and a fully clouded tile
# should come back fully masked. Shadow is tested *relative to the scene*, with
# the absolute value only as a ceiling — a cast shadow is dark compared with its
# surroundings, whereas an absolute cut-off simply rejects every dark scene
# (open water, dense canopy, a low-reflectance winter tile) in its entirety.
CLOUD_BRIGHTNESS_MIN = 0.72
CLOUD_SATURATION_MAX = 0.18
CLOUD_NDVI_MAX = 0.25
SHADOW_BRIGHTNESS_MAX = 0.10
SHADOW_NIR_MAX = 0.12
SHADOW_RELATIVE_FACTOR = 0.45   # fraction of the scene's median brightness
SATURATION_LEVEL = 0.995

# If the shadow heuristic rejects more than this share of a tile it is
# diagnosing itself rather than the imagery, and is discarded.
HEURISTIC_SHADOW_MAX_FRACTION = 0.90


@dataclass
class QualityMask:
    """Per-pixel usability of one observation."""

    valid: np.ndarray            # bool (H, W) — pixels safe to compare
    cloud: np.ndarray            # bool (H, W)
    shadow: np.ndarray           # bool (H, W)
    nodata: np.ndarray           # bool (H, W)
    saturated: np.ndarray        # bool (H, W)
    method: str                  # "scl" | "heuristic" | "scl+heuristic"
    dilation_px: int
    notes: list = field(default_factory=list)

    @property
    def clear_fraction(self) -> float:
        return float(self.valid.mean())

    @property
    def cloud_fraction(self) -> float:
        return float(self.cloud.mean())

    @property
    def shadow_fraction(self) -> float:
        return float(self.shadow.mean())

    @property
    def nodata_fraction(self) -> float:
        return float((self.nodata | self.saturated).mean())

    def summary(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "clear_fraction": round(self.clear_fraction, 4),
            "cloud_fraction": round(self.cloud_fraction, 4),
            "shadow_fraction": round(self.shadow_fraction, 4),
            "nodata_fraction": round(self.nodata_fraction, 4),
            "dilation_px": self.dilation_px,
            "notes": list(self.notes),
        }


def _band(raster: np.ndarray, band_map: Optional[Dict[str, int]], name: str) -> Optional[np.ndarray]:
    if not band_map or name not in band_map:
        return None
    index = band_map[name]
    if not isinstance(index, (int, np.integer)) or index < 0 or index >= raster.shape[-1]:
        return None
    return raster[..., int(index)].astype(np.float32)


def compute_quality_mask(
    raster: np.ndarray,
    band_map: Optional[Dict[str, int]] = None,
    scl: Optional[np.ndarray] = None,
    ingest_mask: Optional[np.ndarray] = None,
    dilation: int = 2,
) -> QualityMask:
    """
    Build the usable-pixel mask for one observation.

    Args:
        raster: (H, W, C) reflectance scaled to [0, 1].
        band_map: band-name -> channel index for the raster.
        scl: raw Sentinel-2 scene-classification codes (H, W), unscaled.
        ingest_mask: the mask computed at ingestion time, if the tile carries one.
        dilation: radius in pixels by which cloud/shadow are grown.
    """
    arr = np.asarray(raster, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[..., None]
    height, width = arr.shape[:2]
    notes: list = []

    finite = np.isfinite(arr).all(axis=-1)
    nodata = (~finite) | np.all(arr == 0.0, axis=-1)
    saturated = np.any(arr >= SATURATION_LEVEL, axis=-1) & finite

    cloud = np.zeros((height, width), dtype=bool)
    shadow = np.zeros((height, width), dtype=bool)
    method = "heuristic"

    if scl is not None and np.asarray(scl).shape[:2] == (height, width):
        codes = np.asarray(scl).astype(np.int32)
        cloud = np.isin(codes, SCL_CLOUD)
        shadow = np.isin(codes, SCL_SHADOW)
        nodata = nodata | np.isin(codes, SCL_NODATA)
        saturated = saturated | np.isin(codes, SCL_SATURATED)
        snow = np.isin(codes, SCL_SNOW)
        if snow.any():
            cloud = cloud | snow
            notes.append("snow/ice pixels treated as unusable")
        method = "scl"
    else:
        visible = arr[..., : min(3, arr.shape[-1])]
        brightness = visible.mean(axis=-1)
        max_c = visible.max(axis=-1)
        min_c = visible.min(axis=-1)
        saturation = (max_c - min_c) / (max_c + 1e-6)
        cloud = (brightness > CLOUD_BRIGHTNESS_MIN) & (saturation < CLOUD_SATURATION_MAX)

        # Scene-relative darkness cut-off, capped by the absolute ceiling.
        finite_brightness = brightness[np.isfinite(brightness)]
        median_brightness = float(np.median(finite_brightness)) if finite_brightness.size else 0.0
        shadow_cut = min(SHADOW_BRIGHTNESS_MAX, SHADOW_RELATIVE_FACTOR * median_brightness)

        nir = _band(arr, band_map, "nir")
        red = _band(arr, band_map, "red")
        if nir is not None and red is not None:
            # Bright bare soil / concrete is also low-saturation; a vegetation
            # test separates it from actual cloud without a thermal band.
            ndvi = (nir - red) / (nir + red + 1e-6)
            cloud &= ndvi < CLOUD_NDVI_MAX
            nir_cut = min(SHADOW_NIR_MAX, SHADOW_RELATIVE_FACTOR * float(np.median(nir)))
            shadow = (brightness < shadow_cut) & (nir < nir_cut)
            notes.append("NIR-assisted cloud/shadow heuristic")
        else:
            shadow = brightness < shadow_cut
            notes.append("RGB-only cloud/shadow heuristic (no NIR band)")

        if shadow.mean() > HEURISTIC_SHADOW_MAX_FRACTION:
            shadow = np.zeros_like(shadow)
            notes.append(
                "shadow heuristic rejected (would have masked the whole tile — "
                "uniformly dark scene, not cast shadow)"
            )

    if dilation > 0:
        cloud = dilate(cloud, dilation)
        shadow = dilate(shadow, dilation)

    valid = ~(nodata | saturated | cloud | shadow)

    if ingest_mask is not None:
        ingest = np.asarray(ingest_mask)
        if ingest.shape[:2] == (height, width):
            valid &= ingest.astype(bool)
            method = f"{method}+ingest"
            notes.append("intersected with ingest-time quality mask")

    return QualityMask(
        valid=valid,
        cloud=cloud,
        shadow=shadow,
        nodata=nodata,
        saturated=saturated,
        method=method,
        dilation_px=int(dilation),
        notes=notes,
    )


def joint_valid_mask(
    before: QualityMask,
    after: QualityMask,
    footprint: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Pixels usable in *both* observations (and inside the co-registered
    footprint, if the warp introduced border fill).
    """
    joint = before.valid & after.valid
    if footprint is not None and np.asarray(footprint).shape == joint.shape:
        joint = joint & np.asarray(footprint, dtype=bool)
    return joint
