"""
Earth-observation feature extractor for change detection — the interface
Prithvi-EO plugs into.

Same honesty contract as embeddings.py:
  - If a staged Prithvi checkpoint + config exist under MODEL_DIR/prithvi,
    we load the real ViT-based Prithvi-EO backbone using Prithvi's official
    HuggingFace-format implementation and weights from local disk, never
    downloaded at runtime, and extract patch-level features.
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
import importlib.util
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from config import settings

logger = logging.getLogger("terrex.prithvi")

PATCH = 16  # Prithvi's native ViT patch size
OFFICIAL_WEIGHTS = "Prithvi_EO_V1_100M.pt"
LEGACY_WEIGHTS = "prithvi_eo_v1.pt"
CONFIG = "config.json"
SOURCE = "prithvi_mae.py"


@dataclass
class FeatureMap:
    array: np.ndarray  # (H_patches, W_patches, C) feature grid
    model_name: str
    is_placeholder: bool


class _RealPrithvi:
    def __init__(self, weights_path: Path, config_path: Path):
        import torch
        self.torch = torch
        source_path = config_path.with_name(SOURCE)
        if not source_path.exists():
            raise RuntimeError(f"Official Prithvi source is missing: {source_path}")
        spec = importlib.util.spec_from_file_location("terrex_prithvi_mae", source_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load the staged official Prithvi implementation")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with config_path.open(encoding="utf-8") as handle:
            config = json.load(handle)["pretrained_cfg"]
        # The official v1 checkpoint is an MAE state dict.  Create the
        # encoder-only model with its documented config, discard fixed
        # positional embeddings, then load exactly as the upstream inference
        # script does.
        self.model = module.PrithviMAE(**config, encoder_only=True)
        try:
            checkpoint = torch.load(weights_path, map_location="cpu", weights_only=True)
        except TypeError:  # Older Torch versions do not support weights_only.
            checkpoint = torch.load(weights_path, map_location="cpu")
        state_dict = self._state_dict_from_checkpoint(checkpoint)
        state_dict = {
            key.removeprefix("module."): value
            for key, value in state_dict.items()
            if "pos_embed" not in key
        }
        incompatible = self.model.load_state_dict(state_dict, strict=False)
        unexpected = [key for key in incompatible.unexpected_keys if not key.startswith("decoder.")]
        if unexpected:
            raise RuntimeError(f"Unexpected Prithvi checkpoint keys: {unexpected[:3]}")
        self.model.eval()
        self.mean = np.asarray(config["mean"], dtype=np.float32)[:, None, None]
        self.std = np.asarray(config["std"], dtype=np.float32)[:, None, None]
        self.model_name = "prithvi-eo-1.0-100m"

    @staticmethod
    def _state_dict_from_checkpoint(checkpoint: object) -> Mapping[str, object]:
        if not isinstance(checkpoint, Mapping):
            raise RuntimeError("Prithvi checkpoint is not a state dict")
        for key in ("model", "state_dict", "module"):
            nested = checkpoint.get(key)
            if isinstance(nested, Mapping):
                return nested
        return checkpoint

    def extract(self, image_chw: np.ndarray) -> np.ndarray:
        if image_chw.shape[0] != 6:
            raise ValueError("Prithvi-EO-1.0 requires six bands: blue, green, red, NIR, SWIR1, SWIR2")
        image_chw = image_chw.astype(np.float32, copy=False)
        # Input reflectance is stored as [0, 1] by TerreX; Prithvi was trained
        # on HLS reflectance scaled to [0, 10000].
        if image_chw.max() <= 1.5:
            image_chw = image_chw * 10000.0
        image_chw = (image_chw - self.mean) / self.std
        with self.torch.no_grad():
            tensor = self.torch.from_numpy(image_chw).unsqueeze(0).unsqueeze(2).float()
            # Official forward_features returns one tensor per transformer
            # block; its final entry includes the CLS token.
            feats = self.model.forward_features(tensor)[-1][:, 1:, :]
        n = feats.shape[1]
        side = int(round(n ** 0.5))
        if side * side != n:
            raise RuntimeError(f"Prithvi produced a non-square token grid ({n} tokens)")
        return feats.cpu().numpy()[0].reshape(side, side, -1)


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
        weights = settings.PRITHVI_DIR / OFFICIAL_WEIGHTS
        if not weights.exists():
            # Backward-compatible name used by earlier TerreX staging docs.
            weights = settings.PRITHVI_DIR / LEGACY_WEIGHTS
        config = settings.PRITHVI_DIR / CONFIG
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

    @property
    def model_name(self) -> str:
        return self._real.model_name if self._real is not None else self._placeholder.model_name

    def extract(self, image_chw: np.ndarray) -> FeatureMap:
        if self._real is not None and image_chw.shape[0] == 6:
            arr = self._real.extract(image_chw)
            return FeatureMap(arr, self._real.model_name, False)
        arr = self._placeholder.extract(image_chw)
        return FeatureMap(arr, self._placeholder.model_name, True)


prithvi_service = PrithviService()
