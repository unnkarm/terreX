"""
Per-pixel false-alarm suppression — stage 10 of the change pipeline.

services.false_alarm scores the *scene*: it decides how much to trust the
detection as a whole. This module works one level down, on the map itself,
removing the pixels that a scene-level score cannot reach:

  1. **Unusable pixels.** Cloud, shadow, saturated and nodata pixels carry no
     change information, so their probability is zeroed outright.
  2. **Registration residual.** Sub-pixel misalignment produces change along
     strong edges and nowhere else. High-gradient pixels are discounted in
     proportion to the misalignment measured *after* warping — never in
     proportion to the before/after correlation, which genuine ground change
     depresses just as misalignment does.
  3. **Context corroboration.** A pixel whose neighbourhood did not also change
     is speckle. Scores are scaled by local support.
  4. **Morphological cleanup.** Opening plus a minimum-region-size filter drops
     the remaining isolated detections that survive step 3.

Every stage records how much area it removed, so the evidence panel can show
which suppressor was responsible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from services.algorithms.evidence import context_support
from services.algorithms.imageops import (
    gradient_magnitude,
    morphological_open,
    remove_small_regions,
    to_gray,
)

# Fraction of a pixel's score that registration residual may remove.
MAX_EDGE_PENALTY = 0.8
# Residual shift (px) at which the edge penalty is fully applied.
RESIDUAL_SATURATION_PX = 2.0
# Severity assumed when co-registration failed outright and no residual could
# be measured — half the maximum penalty, since the misalignment is unknown
# rather than known to be large.
UNREGISTERED_SEVERITY = 0.5
# Neighbourhood change fraction at which a pixel is considered fully supported.
FULL_SUPPORT_FRACTION = 0.35
# Score retained by a pixel with no neighbourhood support at all.
UNSUPPORTED_RETENTION = 0.55


@dataclass
class SuppressionMaps:
    probability: np.ndarray                 # (H, W) suppressed change probability
    mask: np.ndarray                        # (H, W) uint8 final binary change mask
    stages: List[Dict[str, Any]] = field(default_factory=list)
    changed_pixels: int = 0
    changed_fraction: float = 0.0
    removed_fraction: float = 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "stages": list(self.stages),
            "changed_pixels": int(self.changed_pixels),
            "changed_fraction": round(float(self.changed_fraction), 5),
            "removed_fraction": round(float(self.removed_fraction), 5),
        }


def suppress_false_alarms(
    probability: np.ndarray,
    valid: Optional[np.ndarray],
    before_raster: np.ndarray,
    threshold: float = 0.5,
    residual_shift_px: float = 0.0,
    registration_aligned: bool = True,
    context_radius: int = 3,
    min_region_pixels: int = 8,
    open_radius: int = 1,
) -> SuppressionMaps:
    """Apply the per-pixel suppressors in order and return the cleaned mask."""
    probability = np.asarray(probability, dtype=np.float32).copy()
    height, width = probability.shape[:2]
    stages: List[Dict[str, Any]] = []

    initial_mask = probability > threshold
    initial_count = int(initial_mask.sum())

    def _record(name: str, detail: str, before_count: int, current: np.ndarray) -> int:
        after_count = int((current > threshold).sum())
        removed = max(before_count - after_count, 0)
        stages.append({
            "stage": name,
            "detail": detail,
            "pixels_before": before_count,
            "pixels_after": after_count,
            "pixels_removed": removed,
        })
        return after_count

    # 1. Unusable pixels carry no evidence.
    running = initial_count
    if valid is not None:
        valid_mask = np.asarray(valid, dtype=bool)
        probability *= valid_mask
        running = _record(
            "quality_masking",
            f"Zeroed {int((~valid_mask).sum())} cloud/shadow/nodata pixel(s) "
            f"({float((~valid_mask).mean()) * 100:.1f}% of the tile).",
            running,
            probability,
        )

    # 2. Registration residual concentrates on edges.
    #
    # Severity comes from the misalignment *measured after warping*, never from
    # the before/after correlation: genuine ground change lowers that
    # correlation too, so keying the penalty off it would suppress exactly the
    # detections the pipeline exists to find.
    residual = float(abs(residual_shift_px))
    residual_severity = min(1.0, residual / RESIDUAL_SATURATION_PX)
    if not registration_aligned:
        residual_severity = max(residual_severity, UNREGISTERED_SEVERITY)
    if residual_severity > 0.02:
        edges = gradient_magnitude(to_gray(before_raster))
        edge_scale = float(np.percentile(edges, 95)) or 1.0
        edge_strength = np.clip(edges / (edge_scale + 1e-6), 0.0, 1.0)
        penalty = MAX_EDGE_PENALTY * residual_severity * edge_strength
        probability *= 1.0 - penalty
        running = _record(
            "registration_residual",
            f"Residual misalignment {residual:.2f}px"
            + ("" if registration_aligned else " (pair not co-registered)")
            + f" — edge pixels discounted by up to {MAX_EDGE_PENALTY * residual_severity * 100:.0f}%.",
            running,
            probability,
        )
    else:
        stages.append({
            "stage": "registration_residual",
            "detail": (
                f"Alignment residual negligible ({residual:.2f}px) — no edge discount applied."
            ),
            "pixels_before": running,
            "pixels_after": running,
            "pixels_removed": 0,
        })

    # 3. Context corroboration — isolated pixels are speckle, not ground change.
    support = context_support(probability, threshold, context_radius)
    support_factor = UNSUPPORTED_RETENTION + (1.0 - UNSUPPORTED_RETENTION) * np.clip(
        support / FULL_SUPPORT_FRACTION, 0.0, 1.0
    )
    probability *= support_factor
    running = _record(
        "context_corroboration",
        f"Scores scaled by neighbourhood support over a {2 * context_radius + 1}px window "
        f"(unsupported pixels retain {UNSUPPORTED_RETENTION:.0%}).",
        running,
        probability,
    )

    # 4. Morphological cleanup on the binarised mask.
    mask = probability > threshold
    mask = morphological_open(mask, open_radius)
    mask = remove_small_regions(mask, min_region_pixels)
    dropped = int((probability > threshold).sum() - mask.sum())
    # Keep the continuous map consistent with the binary mask: pixels the
    # cleanup removed are pushed just below threshold rather than to zero, so
    # the rendered overlay still shows the faint signal that was rejected.
    probability = np.where(mask, probability, np.minimum(probability, threshold * 0.9)).astype(np.float32)
    stages.append({
        "stage": "morphological_cleanup",
        "detail": (
            f"Opening (r={open_radius}) plus minimum region size {min_region_pixels}px "
            f"removed {max(dropped, 0)} speckle pixel(s)."
        ),
        "pixels_before": running,
        "pixels_after": int(mask.sum()),
        "pixels_removed": max(dropped, 0),
    })

    changed_pixels = int(mask.sum())
    total_pixels = max(height * width, 1)
    return SuppressionMaps(
        probability=probability,
        mask=mask.astype(np.uint8),
        stages=stages,
        changed_pixels=changed_pixels,
        changed_fraction=changed_pixels / total_pixels,
        removed_fraction=(initial_count - changed_pixels) / max(initial_count, 1),
    )
