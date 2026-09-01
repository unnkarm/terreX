"""
Earth-observation feature extractor for change detection — the interface
Prithvi-EO plugs into.

Same honesty contract as embeddings.py:
  - If a staged Prithvi checkpoint + config exist under MODEL_DIR/prithvi,
    we load the real ViT-based Prithvi-EO backbone (via terratorch /
    Prithvi's official HuggingFace-format weights loaded from local disk,
    never downloaded at runtime) and extract patch-level features.
  - Otherwise we fall back to a transparent, non-AI statistical feature
    extractor (per-patch band statistics + simple texture measures) so
    Feature 5 (change detection) is fully wired end-to-end. Every result
    is tagged `is_placeholder_model=True` with method
    "feature-diff-placeholder", matching the spec's explicit instruction:
    "Start with a simple feature-difference approach if a trained change
    model is unavailable."
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from config import settings

logger = logging.getLogger("terrex.prithvi")

PATCH = 16  # Prithvi's native ViT patch size


@dataclass
class FeatureMap:
    array: np.ndarray  # (H_patches, W_patches, C) feature grid
    model_name: str
    is_placeholder: bool


class _RealPrithvi:
    def __init__(self, weights_path: Path, config_path: Path):
        import torch
        # NOTE: real integration point. Prithvi-EO is distributed as a
        # ViT-style masked-autoencoder backbone; loading code depends on
        # which release is staged (terratorch vs. raw HF checkpoint). We
        # keep this isolated so swapping the loader doesn't touch callers.
        from terratorch.models import PrithviViT  # type: ignore

        self.torch = torch
        self.model = PrithviViT.from_pretrained_local(weights_path, config_path)
        self.model.eval()
        self.model_name = "prithvi-eo-v1"

    def extract(self, image_chw: np.ndarray) -> np.ndarray:
        with self.torch.no_grad():
            tensor = self.torch.from_numpy(image_chw).unsqueeze(0).float()
            feats = self.model.forward_features(tensor)  # (1, N, C)
        n = feats.shape[1]
        side = int(round(n ** 0.5))
        return feats.numpy()[0].reshape(side, side, -1)


class _PlaceholderFeatureExtractor:
    """
    Non-AI, transparent statistical feature extractor. Produces a per-patch
    feature vector [mean_R, mean_G, mean_B, std_R, std_G, std_B, edge_energy]
    so change detection has something real (if simple) to diff.
    """

    model_name = "statistical-patch-features-placeholder"

    def __init__(self, patch: int = PATCH):
        self.patch = patch

    def extract(self, image_chw: np.ndarray) -> np.ndarray:
        c, h, w = image_chw.shape
        ph = h // self.patch
        pw = w // self.patch
        feats = np.zeros((ph, pw, c * 2 + 1), dtype=np.float32)
        for i in range(ph):
            for j in range(pw):
                patch = image_chw[
                    :, i * self.patch:(i + 1) * self.patch, j * self.patch:(j + 1) * self.patch
                ]
                means = patch.reshape(c, -1).mean(axis=1)
                stds = patch.reshape(c, -1).std(axis=1)
                gray = patch.mean(axis=0)
                edge = float(np.abs(np.diff(gray, axis=0)).mean() + np.abs(np.diff(gray, axis=1)).mean())
                feats[i, j] = np.concatenate([means, stds, [edge]])
        return feats


class PrithviService:
    def __init__(self):
        self._real: Optional[_RealPrithvi] = None
        weights = settings.PRITHVI_DIR / "prithvi_eo_v1.pt"
        config = settings.PRITHVI_DIR / "config.json"
        if weights.exists() and config.exists():
            try:
                self._real = _RealPrithvi(weights, config)
                logger.info("Loaded real Prithvi-EO backbone.")
            except Exception as exc:  # pragma: no cover
                logger.warning("Prithvi checkpoint found but failed to load (%s). Using placeholder.", exc)
        else:
            logger.warning(
                "No Prithvi-EO checkpoint staged in %s. Using PLACEHOLDER "
                "statistical feature extractor for change detection — see "
                "README for staging instructions.", settings.PRITHVI_DIR
            )
        self._placeholder = _PlaceholderFeatureExtractor()

    @property
    def is_placeholder(self) -> bool:
        return self._real is None

    def extract(self, image_chw: np.ndarray) -> FeatureMap:
        if self._real is not None:
            arr = self._real.extract(image_chw)
            return FeatureMap(arr, self._real.model_name, False)
        arr = self._placeholder.extract(image_chw)
        return FeatureMap(arr, self._placeholder.model_name, True)


prithvi_service = PrithviService()
