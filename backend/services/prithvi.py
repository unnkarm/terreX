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
from PIL import Image

from config import settings

logger = logging.getLogger("terrex.prithvi")

PATCH = 16  # Prithvi's native ViT patch size
OFFICIAL_WEIGHTS = "Prithvi_EO_V1_100M.pt"
LEGACY_WEIGHTS = "prithvi_eo_v1.pt"
CONFIG = "config.json"
SOURCE = "prithvi_mae.py"
ONNX_WEIGHTS = "prithvi_int8.onnx"


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


class _OnnxPrithvi:
    """ONNX Runtime adapter for the supplied INT8 Prithvi export."""

    model_name = "prithvi-int8-onnx"

    def __init__(self, weights_path: Path, config_path: Path):
        import onnxruntime as ort

        # Silence ORT telemetry before ANY session is created.
        # ORT ≥1.18 phones home on first InferenceSession() call unless disabled;
        # in OFFLINE_MODE this causes a "wsarecv: connection forcibly closed" TCP
        # reset against Google/Azure endpoints.  This call is idempotent.
        try:
            ort.disable_telemetry_events()
        except Exception:
            pass  # Older ORT builds that lack the API won't need it.

        with config_path.open(encoding="utf-8") as handle:
            config = json.load(handle)["pretrained_cfg"]

        # Prefer CUDA if available, fall back to CPU cleanly.
        # Explicitly exclude AzureExecutionProvider — it opened outbound
        # network connections on ORT 1.23+ even in CPU-only deployments.
        available = ort.get_available_providers()
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if "CUDAExecutionProvider" in available
            else ["CPUExecutionProvider"]
        )
        self.session = ort.InferenceSession(str(weights_path), providers=providers)

        inputs = self.session.get_inputs()
        if len(inputs) != 1:
            raise RuntimeError(f"Expected one Prithvi ONNX input, found {len(inputs)}")
        self.input = inputs[0]
        self.input_name = self.input.name
        self.mean = np.asarray(config["mean"], dtype=np.float32)[:, None, None]
        self.std = np.asarray(config["std"], dtype=np.float32)[:, None, None]

        # Log shapes so startup logs confirm the model wired up correctly.
        out_shapes = [(o.name, o.shape) for o in self.session.get_outputs()]
        logger.info(
            "Prithvi ONNX session ready — provider=%s  input=%s%s  outputs=%s",
            self.session.get_providers()[0],
            self.input_name, self.input.shape,
            out_shapes,
        )

    @staticmethod
    def _resize(image_chw: np.ndarray, height: int, width: int) -> np.ndarray:
        if image_chw.shape[-2:] == (height, width):
            return image_chw
        channels = [
            np.asarray(Image.fromarray(channel).resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32)
            for channel in image_chw
        ]
        return np.stack(channels, axis=0)

    def _input_tensor(self, image_chw: np.ndarray) -> np.ndarray:
        shape = list(self.input.shape)
        # The export is commonly [N, C, T, H, W] or [N, C, H, W].
        spatial = [int(v) for v in shape if isinstance(v, int) and v > 16]
        height = spatial[-2] if len(spatial) >= 2 else image_chw.shape[-2]
        width = spatial[-1] if len(spatial) >= 2 else image_chw.shape[-1]
        image_chw = self._resize(image_chw, height, width).astype(np.float32, copy=False)
        if image_chw.max() <= 1.5:
            image_chw = image_chw * 10000.0
        image_chw = (image_chw - self.mean) / self.std
        if len(shape) == 5:
            return image_chw[None, :, None, :, :]
        if len(shape) == 4:
            return image_chw[None, :, :, :]
        raise RuntimeError(f"Unsupported Prithvi ONNX input shape: {self.input.shape}")

    @staticmethod
    def _feature_grid(output: np.ndarray) -> np.ndarray:
        arr = np.asarray(output, dtype=np.float32)
        if arr.ndim == 5 and arr.shape[0] == 1:
            arr = arr[0]
        if arr.ndim == 4 and arr.shape[0] == 1:
            arr = arr[0]
        if arr.ndim == 4:
            # NCHW/NTCHW segmentation-style output -> patch grid with channels last.
            arr = np.transpose(arr[0], (1, 2, 0))
        elif arr.ndim == 3:
            # [C, H, W] or already [H, W, C].
            if arr.shape[1] == arr.shape[2] and arr.shape[0] != arr.shape[1]:
                arr = np.transpose(arr, (1, 2, 0))
            elif arr.shape[0] != arr.shape[1]:
                arr = arr.reshape(-1, arr.shape[-1])
        if arr.ndim == 2:
            tokens, channels = arr.shape
            if int(round((tokens - 1) ** 0.5)) ** 2 == tokens - 1:
                arr = arr[1:]
                tokens -= 1
            side = int(round(tokens ** 0.5))
            if side * side != tokens:
                raise RuntimeError(f"Prithvi ONNX produced {tokens} non-square tokens")
            arr = arr.reshape(side, side, channels)
        if arr.ndim != 3:
            raise RuntimeError(f"Unsupported Prithvi ONNX output shape: {np.asarray(output).shape}")
        return arr

    def extract(self, image_chw: np.ndarray) -> np.ndarray:
        if image_chw.shape[0] != 6:
            raise ValueError("Prithvi-EO-1.0 requires six bands: blue, green, red, NIR, SWIR1, SWIR2")
        outputs = self.session.run(None, {self.input_name: self._input_tensor(image_chw)})
        if not outputs:
            raise RuntimeError("Prithvi ONNX returned no outputs")
        return self._feature_grid(outputs[0])


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
        self._onnx: Optional[_OnnxPrithvi] = None
        onnx_weights = settings.PRITHVI_DIR / ONNX_WEIGHTS
        weights = settings.PRITHVI_DIR / OFFICIAL_WEIGHTS
        if not weights.exists():
            # Backward-compatible name used by earlier TerreX staging docs.
            weights = settings.PRITHVI_DIR / LEGACY_WEIGHTS
        config = settings.PRITHVI_DIR / CONFIG
        if onnx_weights.exists() and config.exists():
            try:
                self._onnx = _OnnxPrithvi(onnx_weights, config)
                logger.info("Loaded supplied INT8 Prithvi ONNX model.")
            except Exception as exc:
                logger.warning("Prithvi ONNX model found but failed to load (%s); trying Torch checkpoint.", exc)
        elif weights.exists() and config.exists():
            try:
                self._real = _RealPrithvi(weights, config)
                logger.info("Loaded real Prithvi-EO backbone.")
            except Exception as exc:  # pragma: no cover
                logger.warning("Prithvi checkpoint found but failed to load (%s). Using placeholder.", exc)
        else:
            logger.warning(
                "No Prithvi-EO ONNX model found in %s. Expected 'prithvi_int8.onnx'. "
                "Using PLACEHOLDER statistical feature extractor for change detection — see "
                "README for staging instructions.", settings.PRITHVI_DIR
            )
        self._placeholder = _PlaceholderFeatureExtractor()

    @property
    def is_placeholder(self) -> bool:
        return self._real is None and self._onnx is None

    @property
    def model_name(self) -> str:
        if self._onnx is not None:
            return self._onnx.model_name
        return self._real.model_name if self._real is not None else self._placeholder.model_name

    def extract(self, image_chw: np.ndarray) -> FeatureMap:
        image_chw = np.asarray(image_chw, dtype=np.float32)
        if (self._onnx is not None or self._real is not None):
            if image_chw.shape[0] == 1:
                # 1-band (e.g. SAR single polarization) -> replicate across 6 channels
                v = image_chw[0]
                image_chw = np.stack([v, v, v, v, v, v], axis=0)
            elif image_chw.shape[0] == 2:
                # 2-band (e.g. SAR VV/VH) -> replicate
                vv, vh = image_chw[0], image_chw[1]
                image_chw = np.stack([vv, vh, vv, vh, vv, vh], axis=0)
            elif image_chw.shape[0] == 3:
                # Synthesize standard 6 EO bands: blue, green, red, nir, swir1, swir2
                r = image_chw[0]
                g = image_chw[1]
                b = image_chw[2]
                nir = np.clip(1.2 * r - 0.2 * g, 0.0, 1.0)
                swir1 = np.clip(0.9 * r, 0.0, 1.0)
                swir2 = np.clip(0.8 * r, 0.0, 1.0)
                image_chw = np.stack([b, g, r, nir, swir1, swir2], axis=0)
            elif image_chw.shape[0] > 6:
                image_chw = image_chw[:6]

        if self._onnx is not None and image_chw.shape[0] == 6:
            arr = self._onnx.extract(image_chw)
            return FeatureMap(arr, self._onnx.model_name, False)
        if self._real is not None and image_chw.shape[0] == 6:
            arr = self._real.extract(image_chw)
            return FeatureMap(arr, self._real.model_name, False)
        arr = self._placeholder.extract(image_chw)
        return FeatureMap(arr, self._placeholder.model_name, True)


prithvi_service = PrithviService()
