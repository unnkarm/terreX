"""
Generates a set of synthetic but *geospatially and spectrally valid* multi-band GeoTIFF scenes
for demoing TerreX fully offline, with:
  - 6 spectral bands: Blue, Green, Red, NIR, SWIR1, and SCL (Scene Classification Layer)
  - Realistic CRS / transform / bounds (rasterio + real WGS84 coordinates)
  - A winding "river", dynamic "vegetation", growing "settlement", and expanding "road"
  - Injected cloud / haze patches in some scenes to exercise false-alarm suppression (2.2.3)
  - Full support for spectral index calculation (NDVI, NDWI, NDBI) and 4-class change typing (2.2.2)

This is NOT a substitute for real satellite granules — it provides a guaranteed reproducible,
fully air-gapped test fixture. Real GeoTIFF/COG granules go through the exact same code path.
"""
from __future__ import annotations

import numpy as np
import rasterio
from rasterio.transform import from_origin
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "incoming"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Centred near a demo river valley AOI (lon/lat, WGS84)
ORIGIN_LON, ORIGIN_LAT = 77.20, 28.60
PIXEL_SIZE_DEG = 0.0002  # ~20m equivalent per pixel
SIZE = 512


def _base_scene(rng: np.random.Generator, settlement_size: int, road_length: int, cloud: bool, sensor: str) -> np.ndarray:
    """
    Generate 6-band synthetic satellite raster:
    Band 0: Blue  (490nm)
    Band 1: Green (560nm)
    Band 2: Red   (665nm)
    Band 3: NIR   (842nm)   - High in vegetation, very low in water
    Band 4: SWIR1 (1610nm)  - High in built-up / dry soil, very low in water
    Band 5: SCL   (Scene Classification Layer: 4=veg, 5=built/bare, 6=water, 8=shadow, 9=cloud)
    """
    img = np.zeros((6, SIZE, SIZE), dtype=np.uint8)

    # 1. Background terrain (vegetation-rich ground)
    base_veg = rng.integers(50, 75, size=(SIZE, SIZE), dtype=np.uint8)
    img[0] = (base_veg * 0.5).astype(np.uint8)   # Blue: low
    img[1] = (base_veg * 0.9).astype(np.uint8)   # Green: medium
    img[2] = (base_veg * 0.4).astype(np.uint8)   # Red: low (chlorophyll absorption)
    img[3] = (base_veg * 2.8).clip(0, 240).astype(np.uint8) # NIR: strong reflectance
    img[4] = (base_veg * 0.7).astype(np.uint8)   # SWIR1: moderate
    img[5] = 4                                  # SCL: 4 = Vegetation

    # 2. A winding river following a sine curve
    xs = np.arange(SIZE)
    river_center = (SIZE // 2 + 60 * np.sin(xs / 60.0)).astype(int)
    river_width = 12
    for x in xs:
        y0 = max(0, river_center[x] - river_width)
        y1 = min(SIZE, river_center[x] + river_width)
        img[0, y0:y1, x] = 170  # High Blue
        img[1, y0:y1, x] = 110  # Moderate Green
        img[2, y0:y1, x] = 40   # Low Red
        img[3, y0:y1, x] = 15   # Very low NIR (strong water absorption)
        img[4, y0:y1, x] = 10   # Very low SWIR
        img[5, y0:y1, x] = 6    # SCL: 6 = Water

    # 3. Settlement growing over time near the river bank (Construction / Built-up)
    cx, cy = SIZE // 2 + 100, SIZE // 2 - 50
    half = settlement_size // 2
    if settlement_size > 0:
        x0, x1 = max(0, cx - half), min(SIZE, cx + half)
        y0, y1 = max(0, cy - half), min(SIZE, cy + half)
        block = rng.integers(160, 230, size=(y1 - y0, x1 - x0), dtype=np.uint8)
        img[0, y0:y1, x0:x1] = (block * 0.8).astype(np.uint8) # Blue
        img[1, y0:y1, x0:x1] = (block * 0.85).astype(np.uint8) # Green
        img[2, y0:y1, x0:x1] = block                          # Red: high
        img[3, y0:y1, x0:x1] = (block * 0.75).astype(np.uint8) # NIR: moderate
        img[4, y0:y1, x0:x1] = (block * 1.1).clip(0, 255).astype(np.uint8) # SWIR1: very high (built-up)
        img[5, y0:y1, x0:x1] = 5                              # SCL: 5 = Bare / Built

    # 4. Road corridor development (Linear feature)
    if road_length > 0:
        rx_start = cx
        ry_start = cy + half
        rx_end = min(SIZE - 10, rx_start + road_length)
        ry_end = min(SIZE - 10, ry_start + (road_length // 3))
        # Draw a narrow linear road strip (width = 4)
        for t in np.linspace(0, 1, road_length * 2):
            rx = int(rx_start + t * (rx_end - rx_start))
            ry = int(ry_start + t * (ry_end - ry_start))
            if 0 <= rx < SIZE - 4 and 0 <= ry < SIZE - 4:
                img[0:3, ry:ry+3, rx:rx+3] = 140 # Gray asphalt/gravel
                img[3, ry:ry+3, rx:rx+3] = 90    # Low NIR
                img[4, ry:ry+3, rx:rx+3] = 190   # High SWIR
                img[5, ry:ry+3, rx:rx+3] = 5     # SCL: 5 = Built/Road

    # 5. Cloud / Haze patch injection
    if cloud:
        cyx, cyy = rng.integers(SIZE // 4, 3 * SIZE // 4, 2)
        yy, xx = np.ogrid[:SIZE, :SIZE]
        mask = (xx - cyx) ** 2 + (yy - cyy) ** 2 < (SIZE // 5) ** 2
        img[0:5, mask] = 240  # Bright reflectance across all bands
        img[5, mask] = 9      # SCL: 9 = High probability cloud

    return img


def generate(n_dates: int = 8):
    rng = np.random.default_rng(42)
    transform = from_origin(ORIGIN_LON, ORIGIN_LAT, PIXEL_SIZE_DEG, PIXEL_SIZE_DEG)
    dates = [
        "20230101", "20230601",
        "20240101", "20240601",
        "20250101", "20250601",
        "20260101", "20260601"
    ][:n_dates]
    settlement_sizes = [40, 60, 90, 120, 150, 180, 210, 240]  # Progressive settlement expansion
    road_lengths = [0, 40, 80, 120, 160, 200, 240, 280]       # Progressive road development
    cloud_flags = [False, True, False, False, False, True, False, False]
    sensors = ["Sentinel-2"] * len(dates)

    written = []
    for date, ssize, rlen, cloud, sensor in zip(dates, settlement_sizes, road_lengths, cloud_flags, sensors):
        img = _base_scene(rng, ssize, rlen, cloud, sensor)
        fname = f"{sensor}_{date}_demoAOI.tif"
        path = OUT_DIR / fname
        with rasterio.open(
            path, "w", driver="GTiff", height=SIZE, width=SIZE, count=6,
            dtype=img.dtype, crs="EPSG:4326", transform=transform,
        ) as dst:
            dst.write(img)
            dst.update_tags(
                SENSOR=sensor,
                ACQUISITION_DATE=f"{date[:4]}-{date[4:6]}-{date[6:]}",
                BAND_NAMES="BLUE,GREEN,RED,NIR,SWIR1,SCL",
            )
            # Set band descriptions
            for idx, name in enumerate(["Blue", "Green", "Red", "NIR", "SWIR1", "SCL"], start=1):
                dst.set_band_description(idx, name)
        written.append(str(path))
        print(f"Wrote {path} (6 bands, {SIZE}x{SIZE})")
    return written


if __name__ == "__main__":
    generate()
