"""
Download the real RemoteCLIP ViT-B/32 foundation model weights
from Hugging Face into models/remoteclip/RemoteCLIP-ViT-B-32.pt.

Once downloaded:
1. The backend automatically switches from 'placeholder-visual-hash' to real RemoteCLIP.
2. Ingestion and semantic search use 512-dim vision-language embeddings trained on 800k+ satellite-text pairs.
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path
import urllib.request
import hashlib

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("terrex.download_remoteclip")

# Direct download URL for RemoteCLIP ViT-B/32 PyTorch checkpoint from Hugging Face
REMOTECLIP_HF_URL = "https://huggingface.co/chendelong/RemoteCLIP/resolve/main/RemoteCLIP-ViT-B-32.pt"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = PROJECT_ROOT / "models" / "remoteclip"
TARGET_FILE = TARGET_DIR / "RemoteCLIP-ViT-B-32.pt"


def reporthook(block_num, block_size, total_size):
    """Progress indicator for file download."""
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(100.0, (downloaded / total_size) * 100.0)
        mb_down = downloaded / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)
        sys.stdout.write(f"\rDownloading RemoteCLIP-ViT-B-32.pt: {percent:.1f}% ({mb_down:.1f} MB / {mb_total:.1f} MB)")
        sys.stdout.flush()
    else:
        sys.stdout.write(f"\rDownloaded {downloaded / (1024 * 1024):.1f} MB...")
        sys.stdout.flush()


def download_remoteclip_weights(force: bool = False):
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    if TARGET_FILE.exists() and not force:
        size_mb = TARGET_FILE.stat().st_size / (1024 * 1024)
        logger.info("RemoteCLIP checkpoint already exists at %s (%.1f MB).", TARGET_FILE, size_mb)
        logger.info("To re-download, run with --force.")
        return

    logger.info("Starting download of RemoteCLIP ViT-B/32 weights from Hugging Face...")
    logger.info("Source: %s", REMOTECLIP_HF_URL)
    logger.info("Destination: %s", TARGET_FILE)

    try:
        urllib.request.urlretrieve(REMOTECLIP_HF_URL, TARGET_FILE, reporthook=reporthook)
        print("\n")
        logger.info("SUCCESS: RemoteCLIP weights saved to %s", TARGET_FILE)
        size_mb = TARGET_FILE.stat().st_size / (1024 * 1024)
        logger.info("File size: %.1f MB", size_mb)
        logger.info("Restart TerreX backend to activate real RemoteCLIP semantic search!")
    except Exception as exc:
        logger.exception("Download failed: %s", exc)
        if TARGET_FILE.exists():
            TARGET_FILE.unlink()
        sys.exit(1)


if __name__ == "__main__":
    force_download = "--force" in sys.argv
    download_remoteclip_weights(force=force_download)
