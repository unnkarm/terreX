"""
Text / image embedding service — the interface RemoteCLIP plugs into.

Design goal: the rest of the codebase (search.py, ingestion.py) only calls
`embed_text()` / `embed_image()` and never knows whether it got a real
RemoteCLIP embedding or a placeholder. This keeps the model swappable.

HONESTY CONTRACT (per project constraints — "do not fake AI results"):
  - If real RemoteCLIP weights are staged at MODEL_DIR/remoteclip, we load
    them via open_clip's CLIP architecture (RemoteCLIP ships as a CLIP
    fine-tune, so it loads with the standard `open_clip` ViT-B-32 / RN50
    checkpoint loader) and produce real embeddings.
  - If they are NOT staged, we do not pretend. We fall back to a
    deterministic, content-derived embedding (perceptual hash + colour/
    texture statistics projected into the same vector space) purely so the
    rest of the pipeline (Qdrant indexing, ranking, UI) is exercisable
    end-to-end. Every embedding produced this way is tagged
    `is_placeholder=True` and `model_name="placeholder-visual-hash"`, and the
    API surfaces this flag on every result so an analyst is never misled
    into thinking it's semantic AI similarity.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from config import settings

logger = logging.getLogger("terrex.embeddings")

REMOTECLIP_CHECKPOINT_CANDIDATES = [
    "RemoteCLIP-ViT-B-32.pt",
    "RemoteCLIP-RN50.pt",
    "remoteclip.pt",
]


@dataclass
class EmbeddingResult:
    vector: np.ndarray
    model_name: str
    is_placeholder: bool


class _RealRemoteCLIP:
    """Loads an actual RemoteCLIP checkpoint via open_clip, fully offline."""

    def __init__(self, checkpoint_path: Path):
        import open_clip  # local import: heavy dep, only needed on real path
        import torch

        self.torch = torch
        arch = "ViT-B-32" if "ViT-B-32" in checkpoint_path.name else "RN50"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            arch, pretrained=None
        )
        state_dict = torch.load(checkpoint_path, map_location="cpu")
        self.model.load_state_dict(state_dict)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(arch)
        self.model_name = f"remoteclip-{arch.lower()}"

    def embed_text(self, text: str) -> np.ndarray:
        with self.torch.no_grad():
            tokens = self.tokenizer([text])
            feats = self.model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.numpy()[0].astype(np.float32)

    def embed_image(self, image: Image.Image) -> np.ndarray:
        with self.torch.no_grad():
            tensor = self.preprocess(image).unsqueeze(0)
            feats = self.model.encode_image(tensor)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.numpy()[0].astype(np.float32)


class _PlaceholderVisualEmbedder:
    """
    NOT semantic AI. A deterministic, content-derived vector so search /
    ranking / Qdrant / the UI are fully exercisable before real weights are
    staged. Clearly labelled everywhere it's used.
    """

    model_name = "placeholder-visual-hash"

    def __init__(self, dim: int):
        self.dim = dim

    def _project(self, features: np.ndarray) -> np.ndarray:
        # We use a FIXED seed for the projection matrix. If we used a seed based
        # on the image bytes, every slightly different image would get a completely
        # different random matrix, destroying all visual similarity (acting as a
        # cryptographic hash). A constant projection matrix maps similar visual
        # features to similar 512D vectors.
        rng = np.random.default_rng(42)
        proj = rng.standard_normal((features.shape[0], self.dim)).astype(np.float32)
        vec = features @ proj
        norm = np.linalg.norm(vec) + 1e-8
        return (vec / norm).astype(np.float32)

    def embed_image(self, image: Image.Image) -> np.ndarray:
        img = image.convert("RGB").resize((64, 64))
        arr = np.asarray(img, dtype=np.float32) / 255.0
        # cheap, real (not fake) hand-crafted features: per-channel mean/std
        # + coarse 8x8 colour histogram + simple gradient energy (texture)
        means = arr.mean(axis=(0, 1))
        stds = arr.std(axis=(0, 1))
        hist = np.stack([
            np.histogram(arr[..., c], bins=8, range=(0, 1))[0]
            for c in range(3)
        ]).flatten().astype(np.float32)
        hist = hist / (hist.sum() + 1e-8)
        gray = arr.mean(axis=-1)
        gx = np.abs(np.diff(gray, axis=0)).mean()
        gy = np.abs(np.diff(gray, axis=1)).mean()
        features = np.concatenate([means, stds, hist, [gx, gy]])
        return self._project(features)

    def embed_text(self, text: str) -> np.ndarray:
        # Bag-of-character-ngram hashing → deterministic vector. Captures
        # only surface lexical similarity, NOT semantics — intentionally,
        # so nobody mistakes this for real language understanding.
        tokens = text.lower().split()
        feat = np.zeros(64, dtype=np.float32)
        for tok in tokens:
            h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
            feat[h % 64] += 1.0
        feat = feat / (np.linalg.norm(feat) + 1e-8)
        return self._project(feat)


class EmbeddingService:
    def __init__(self):
        self.dim = settings.EMBEDDING_DIM
        self._real: Optional[_RealRemoteCLIP] = None
        self._checkpoint_path = self._find_checkpoint()
        if self._checkpoint_path is not None:
            try:
                self._real = _RealRemoteCLIP(self._checkpoint_path)
                logger.info("Loaded real RemoteCLIP checkpoint: %s", self._checkpoint_path)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Found RemoteCLIP checkpoint but failed to load it (%s). "
                    "Falling back to placeholder embedder.", exc
                )
                self._real = None
        else:
            logger.warning(
                "No RemoteCLIP checkpoint found in %s. Using PLACEHOLDER "
                "visual-hash embeddings — results are wiring-only, not "
                "semantic AI similarity. See README for staging instructions.",
                settings.REMOTECLIP_DIR,
            )
        self._placeholder = _PlaceholderVisualEmbedder(self.dim)

    def _find_checkpoint(self) -> Optional[Path]:
        if not settings.REMOTECLIP_DIR.exists():
            return None
        for name in REMOTECLIP_CHECKPOINT_CANDIDATES:
            p = settings.REMOTECLIP_DIR / name
            if p.exists():
                return p
        # also accept any .pt file the analyst dropped in
        candidates = list(settings.REMOTECLIP_DIR.glob("*.pt"))
        return candidates[0] if candidates else None

    @property
    def is_placeholder(self) -> bool:
        return self._real is None

    def embed_text(self, text: str) -> EmbeddingResult:
        if self._real is not None:
            vec = self._real.embed_text(text)
            return EmbeddingResult(vec, self._real.model_name, False)
        vec = self._placeholder.embed_text(text)
        return EmbeddingResult(vec, self._placeholder.model_name, True)

    def embed_image(self, image: Image.Image) -> EmbeddingResult:
        if self._real is not None:
            vec = self._real.embed_image(image)
            return EmbeddingResult(vec, self._real.model_name, False)
        vec = self._placeholder.embed_image(image)
        return EmbeddingResult(vec, self._placeholder.model_name, True)


# Singleton — model load is expensive, do it once per process.
embedding_service = EmbeddingService()
