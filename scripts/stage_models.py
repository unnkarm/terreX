"""Download and verify the upstream models required for real local inference.

Run this once while online, then operate TerreX offline. The model artifacts
are deliberately Git-ignored and are never fetched by the running backend.
"""
from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
ARTIFACTS = {
    MODELS / "remoteclip" / "RemoteCLIP-ViT-B-32.pt": (
        "https://huggingface.co/chendelong/RemoteCLIP/resolve/main/RemoteCLIP-ViT-B-32.pt?download=true",
        "60014e395d930a3f2963d1d89c8522bf4ad56775571e4356e866864789af85c4",
    ),
    MODELS / "prithvi" / "Prithvi_EO_V1_100M.pt": (
        "https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-1.0-100M/resolve/main/Prithvi_EO_V1_100M.pt?download=true",
        "7fac0c8a8693198e32a055e0c5a967f8b005f382182b63df1b29fdcd5c880731",
    ),
}
SOURCES = {
    MODELS / "prithvi" / "config.json": "https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-1.0-100M/raw/main/config.json",
    MODELS / "prithvi" / "prithvi_mae.py": "https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-1.0-100M/raw/main/prithvi_mae.py",
}


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    temporary.replace(destination)


def main() -> None:
    for destination, (url, expected) in ARTIFACTS.items():
        if not destination.exists() or digest(destination) != expected:
            print(f"Downloading {destination.name}...")
            download(url, destination)
        actual = digest(destination)
        if actual != expected:
            raise RuntimeError(f"Checksum mismatch for {destination}: {actual}")
        print(f"Verified {destination.name}")
    for destination, url in SOURCES.items():
        download(url, destination)
        print(f"Staged {destination.name}")


if __name__ == "__main__":
    main()
