"""Tests for Prithvi-EO architecture and configuration integration."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import numpy as np
import torch

from models.prithvi import (
    PatchEmbed,
    TemporalEncoder,
    LocationEncoder,
    PrithviViT,
    MAEDecoder,
    PrithviMAE,
    get_3d_sincos_pos_embed,
    get_1d_sincos_pos_embed_from_grid,
)
from config import settings

PRITHVI_DIR = settings.PRITHVI_DIR if settings.PRITHVI_DIR.exists() else Path(__file__).resolve().parent.parent / "models" / "prithvi"


def test_prithvi_config_json_valid():
    config_file = PRITHVI_DIR / "config.json"
    assert config_file.exists(), f"Missing config.json in {PRITHVI_DIR}"

    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    assert config["architecture"] == "prithvi_eo_v1_100"
    assert config["num_features"] == 768
    cfg = config["pretrained_cfg"]
    assert cfg["img_size"] == 224
    assert cfg["patch_size"] == [1, 16, 16]
    assert cfg["in_chans"] == 6
    assert cfg["embed_dim"] == 768
    assert cfg["depth"] == 12
    assert cfg["num_heads"] == 12
    assert len(cfg["bands"]) == 6
    assert len(cfg["mean"]) == 6
    assert len(cfg["std"]) == 6


def test_prithvi_vit_instantiation_and_forward():
    config_file = PRITHVI_DIR / "config.json"
    with open(config_file, "r", encoding="utf-8") as f:
        cfg = json.load(f)["pretrained_cfg"]

    model = PrithviViT(
        img_size=cfg["img_size"],
        patch_size=cfg["patch_size"],
        num_frames=cfg["num_frames"],
        in_chans=cfg["in_chans"],
        embed_dim=cfg["embed_dim"],
        depth=cfg["depth"],
        num_heads=cfg["num_heads"],
        mlp_ratio=cfg["mlp_ratio"],
    )
    model.eval()

    # Input shape: (B, C, T, H, W) -> (1, 6, 3, 224, 224)
    x = torch.randn(1, 6, 3, 224, 224)
    with torch.no_grad():
        out, mask, ids_restore = model(x)
        features = model.forward_features(x)

    assert out.shape[-1] == 768
    assert len(features) == cfg["depth"]
    # Last block features include CLS token + patch tokens
    # Grid size: 3 * 14 * 14 = 588 patches + 1 CLS = 589 tokens
    assert features[-1].shape == (1, 589, 768)


def test_prithvi_mae_instantiation():
    config_file = PRITHVI_DIR / "config.json"
    with open(config_file, "r", encoding="utf-8") as f:
        cfg = json.load(f)["pretrained_cfg"]

    mae = PrithviMAE(**cfg, encoder_only=True)
    mae.eval()

    x = torch.randn(1, 6, 3, 224, 224)
    with torch.no_grad():
        feats = mae.forward_features(x)

    assert len(feats) == cfg["depth"]
    assert feats[-1].shape == (1, 589, 768)


def test_prithvi_service_recognizes_config():
    from services.prithvi import prithvi_service
    # Since weights (.pt/.onnx) are not staged, it falls back to placeholder gracefully
    assert prithvi_service is not None
    assert prithvi_service.model_name in ["statistical-patch-features-placeholder", "prithvi-eo-1.0-100m", "prithvi-int8-onnx"]
