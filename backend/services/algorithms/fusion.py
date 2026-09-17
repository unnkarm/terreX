"""
Evidence fusion — stage 9 of the change pipeline.

Combines the independent evidence layers into one probability per pixel. Two
rules govern the combination:

  1. **Reliability weighting.** Each layer's prior weight is scaled by how
     trustworthy it is for this specific pair (placeholder features, RGB-only
     indices, …). A layer that cannot be trusted contributes proportionally
     less rather than being silently dropped.

  2. **Corroboration.** A pixel where every layer agrees keeps its full fused
     score; a pixel supported by only one layer is damped towards
     `CORROBORATION_FLOOR`. This is the whole point of the multi-evidence
     design — a lone embedding spike is no longer sufficient to raise a
     detection, whereas deep + spectral + spatial agreement is decisive.

The per-layer contribution breakdown is kept so the UI can attribute any
detection to the evidence that actually drove it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from services.algorithms.evidence import EvidenceLayer

# A detection with no corroboration retains only this fraction of its score.
CORROBORATION_FLOOR = 0.60


@dataclass
class FusionResult:
    probability: np.ndarray                  # (H, W) fused change probability
    agreement: np.ndarray                    # (H, W) weighted fraction of layers that fired
    weighted_probability: np.ndarray         # (H, W) before the corroboration factor
    weights: Dict[str, float] = field(default_factory=dict)
    contributions: Dict[str, float] = field(default_factory=dict)
    layer_names: List[str] = field(default_factory=list)
    detail: str = ""

    def summary(self, valid: Optional[np.ndarray] = None) -> Dict[str, Any]:
        sample = self.agreement[valid] if valid is not None and np.any(valid) else self.agreement.ravel()
        if sample.size == 0:
            sample = np.zeros(1, dtype=np.float32)
        return {
            "layers": list(self.layer_names),
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "contributions": {k: round(v, 4) for k, v in self.contributions.items()},
            "mean_agreement": round(float(sample.mean()), 4),
            "corroboration_floor": CORROBORATION_FLOOR,
            "detail": self.detail,
        }


def fuse_evidence(
    layers: List[EvidenceLayer],
    valid: Optional[np.ndarray] = None,
    layer_threshold: float = 0.5,
) -> FusionResult:
    """
    Fuse evidence layers into a single corroborated change probability.

    Args:
        layers: independent evidence layers; at least one is required.
        valid: usable-pixel mask used for reporting statistics.
        layer_threshold: probability above which a layer counts as "firing"
            for the corroboration term.
    """
    if not layers:
        raise ValueError("evidence fusion requires at least one layer")

    shape = layers[0].probability.shape
    for layer in layers:
        if layer.probability.shape != shape:
            raise ValueError(
                f"evidence layer '{layer.name}' has shape {layer.probability.shape}, expected {shape}"
            )

    weights = np.asarray([layer.effective_weight for layer in layers], dtype=np.float32)
    total_weight = float(weights.sum())
    if total_weight <= 0.0:
        # Every layer was judged untrustworthy; fall back to an unweighted mean
        # rather than returning a meaningless zero map.
        weights = np.ones_like(weights)
        total_weight = float(weights.sum())

    stacked = np.stack([layer.probability for layer in layers], axis=0).astype(np.float32)
    weight_col = weights[:, None, None]

    weighted = (stacked * weight_col).sum(axis=0) / total_weight
    agreement = ((stacked > layer_threshold).astype(np.float32) * weight_col).sum(axis=0) / total_weight
    probability = np.clip(
        weighted * (CORROBORATION_FLOOR + (1.0 - CORROBORATION_FLOOR) * agreement), 0.0, 1.0
    )

    mask = valid if valid is not None and np.any(valid) else np.ones(shape, dtype=bool)
    contributions = {}
    for layer, weight in zip(layers, weights):
        layer_mean = float(layer.probability[mask].mean())
        contributions[layer.name] = float(weight * layer_mean / total_weight)

    detail = (
        "Reliability-weighted fusion of "
        + ", ".join(f"{layer.name} (w={weight / total_weight:.2f})" for layer, weight in zip(layers, weights))
        + f"; single-layer detections damped to {CORROBORATION_FLOOR:.0%}."
    )

    return FusionResult(
        probability=probability.astype(np.float32),
        agreement=agreement.astype(np.float32),
        weighted_probability=weighted.astype(np.float32),
        weights={layer.name: float(weight / total_weight) for layer, weight in zip(layers, weights)},
        contributions=contributions,
        layer_names=[layer.name for layer in layers],
        detail=detail,
    )
