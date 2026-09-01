"""
Generates a small set of synthetic but *geospatially valid* GeoTIFF scenes
for demoing TerreX fully offline, with:
  - realistic CRS/transform/bounds (rasterio + real WGS84 coordinates)
  - a "river" and "settlement" that grow between two dates, so change
    detection has something genuine (if synthetic) to find
  - injected cloud/haze patches in some scenes, to exercise false-alarm
    suppression (Feature 5)

This is NOT a substitute for real imagery — it exists purely so the full
pipeline (ingest -> embed -> index -> search -> change-detect) can be
demonstrated end-to-end without a network connection. Real GeoTIFF/COG
scenes dropped into data/incoming/ go through the exact same code path.
"""
from __future__ import annotations

import numpy as np
import rasterio
from rasterio.transform import from_origin
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "incoming"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Roughly centred near a fictitious river valley (lon/lat, WGS84)
ORIGIN_LON, ORIGIN_LAT = 77.20, 28.60  # arbitrary demo AOI
PIXEL_SIZE_DEG = 0.0002  # ~ a few tens of metres depending on latitude
SIZE = 512


def _base_scene(rng, settlement_size: int, cloud: bool, sensor: str):
    img = np.zeros((3, SIZE, SIZE), dtype=np.uint8)

    # background terrain (vegetation-ish green/brown noise)
    terrain = 60 + rng.integers(0, 40, size=(SIZE, SIZE))
    img[0] = terrain * 0.6
    img[1] = terrain
    img[2] = terrain * 0.5

    # a winding "river" — blue band following a sine curve
    xs = np.arange(SIZE)
    river_center = (SIZE // 2 + 60 * np.sin(xs / 60.0)).astype(int)
    river_width = 10
    for x in xs:
        y0 = max(0, river_center[x] - river_width)
        y1 = min(SIZE, river_center[x] + river_width)
        img[0, y0:y1, x] = 30
        img[1, y0:y1, x] = 80
        img[2, y0:y1, x] = 160

    # settlement growing over time near the river bank
    cx, cy = SIZE // 2 + 90, SIZE // 2 - 40
    half = settlement_size // 2
    x0, x1 = max(0, cx - half), min(SIZE, cx + half)
    y0, y1 = max(0, cy - half), min(SIZE, cy + half)
    if settlement_size > 0:
        block = rng.integers(150, 220, size=(y1 - y0, x1 - x0))
        img[0, y0:y1, x0:x1] = block
        img[1, y0:y1, x0:x1] = block * 0.9
        img[2, y0:y1, x0:x1] = block * 0.8
        # simple road grid within settlement
        img[:, y0:y1:12, x0:x1] = 90
        img[:, y0:y1, x0:x1:12] = 90

    if cloud:
        cyx, cyy = rng.integers(0, SIZE, 2)
        yy, xx = np.ogrid[:SIZE, :SIZE]
        mask = (xx - cyx) ** 2 + (yy - cyy) ** 2 < (SIZE // 4) ** 2
        img[:, mask] = 235  # bright, low-saturation haze

    return img


def generate(n_dates: int = 5):
    rng = np.random.default_rng(42)
    transform = from_origin(ORIGIN_LON, ORIGIN_LAT, PIXEL_SIZE_DEG, PIXEL_SIZE_DEG)
    dates = ["20230101", "20230401", "20230701", "20231001", "20240101"][:n_dates]
    settlement_sizes = [40, 60, 90, 130, 170]  # grows over time -> real "change"
    cloud_flags = [False, True, False, False, False]  # one cloudy false-alarm case
    sensors = ["SensorA", "SensorA", "SensorB", "SensorA", "SensorB"]

    written = []
    for date, ssize, cloud, sensor in zip(dates, settlement_sizes, cloud_flags, sensors):
        img = _base_scene(rng, ssize, cloud, sensor)
        fname = f"{sensor}_{date}_demoAOI.tif"
        path = OUT_DIR / fname
        with rasterio.open(
            path, "w", driver="GTiff", height=SIZE, width=SIZE, count=3,
            dtype=img.dtype, crs="EPSG:4326", transform=transform,
        ) as dst:
            dst.write(img)
            dst.update_tags(SENSOR=sensor, ACQUISITION_DATE=f"{date[:4]}-{date[4:6]}-{date[6:]}")
        written.append(str(path))
        print(f"Wrote {path}")
    return written


if __name__ == "__main__":
    generate()
