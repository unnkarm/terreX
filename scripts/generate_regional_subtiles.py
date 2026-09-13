"""
Generate dense, high-resolution regional sub-tiles and embeddings for:
  - Salt Lake Sector 5
  - New Town / Rajarhat
  - Howrah (central)

Appends new localized sub-tiles to SQLite DB and upserts new vectors directly
into Qdrant WITHOUT touching, resetting, or deleting any existing vectors.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root and backend to path
ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import json
import logging
import math
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.warp import transform_bounds
from PIL import Image
from shapely.geometry import box
from sqlalchemy import select

from config import settings
from db.database import get_session
from db.models import Scene, Tile
from services.embeddings import embedding_service
from services.vector_store import vector_store
from services.offline_geocoder import offline_geocoder
from services.quality import (
    valid_pixel_fraction, sharpness_score, overall_quality_score
)
from services.algorithms.spectral import compute_spectral_indices
from services.ingestion import (
    _get_dataset_spatial_info, _read_tile_rgb_float, _quality_mask,
    _compute_tile_bounds_wgs84, safe_from_shape, _resolve_band_map,
    DEFAULT_BAND_MAPS, MIN_USABLE_FRACTION
)
from scripts.acquisition_common import REGION_BBOXES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("terrex.regional_subtiles")

REGION_METADATA = {
    "salt_lake_sector_5": {
        "name": "Salt Lake Sector 5",
        "zone": "Bidhannagar / IT Corridor",
        "bbox": REGION_BBOXES["salt_lake_sector_5"],
    },
    "new_town_rajarhat": {
        "name": "New Town / Rajarhat",
        "zone": "New Town Rajarhat",
        "bbox": REGION_BBOXES["new_town_rajarhat"],
    },
    "howrah_central": {
        "name": "Howrah (central)",
        "zone": "Howrah District",
        "bbox": REGION_BBOXES["howrah_central"],
    },
}

TILE_SIZE = 256
STEP_SIZE = 128  # 50% overlap for dense spatial sampling


def _deterministic_subtile_id(scene_id: str, region_key: str, row: int, col: int) -> str:
    key = f"subtile|{scene_id}|{region_key}|{row}|{col}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def generate_subtiles_for_region(
    dataset: rasterio.DatasetReader,
    scene: Scene,
    region_key: str,
    region_info: Dict[str, Any],
    session,
) -> Dict[str, int]:
    crs, transform = _get_dataset_spatial_info(dataset)
    inv = ~transform
    min_lon, min_lat, max_lon, max_lat = region_info["bbox"]

    if crs and str(crs) != "EPSG:4326":
        min_x, min_y, max_x, max_y = transform_bounds("EPSG:4326", crs, min_lon, min_lat, max_lon, max_lat)
    else:
        min_x, min_y, max_x, max_y = min_lon, min_lat, max_lon, max_lat

    c0, r0 = inv * (min_x, max_y)
    c1, r1 = inv * (max_x, min_y)
    min_col, max_col = sorted([int(c0), int(c1)])
    min_row, max_row = sorted([int(r0), int(r1)])

    # Clip to dataset boundary
    min_col = max(0, min_col)
    max_col = min(dataset.width, max_col)
    min_row = max(0, min_row)
    max_row = min(dataset.height, max_row)

    if max_col <= min_col or max_row <= min_row:
        logger.warning("Region %s is outside footprint of scene %s", region_key, scene.scene_id)
        return {"created": 0, "skipped": 0, "discarded": 0}

    sensor = scene.sensor or "MSI"
    band_map = _resolve_band_map(dataset, sensor)
    tile_dir = settings.TILES_DIR / str(scene.scene_id)
    tile_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0
    discarded = 0

    # Grid search with STEP_SIZE inside the regional bounding box
    for row in range(min_row, max_row, STEP_SIZE):
        for col in range(min_col, max_col, STEP_SIZE):
            tile_w = min(TILE_SIZE, dataset.width - col)
            tile_h = min(TILE_SIZE, dataset.height - row)
            if tile_h < TILE_SIZE // 2 or tile_w < TILE_SIZE // 2:
                continue

            window = Window(col_off=col, row_off=row, width=tile_w, height=tile_h)
            subtile_id = _deterministic_subtile_id(str(scene.scene_id), region_key, row, col)

            # Check if tile already exists in DB
            if session.query(Tile.tile_id).filter(Tile.tile_id == subtile_id).first():
                skipped += 1
                continue

            rgb_patch = _read_tile_rgb_float(dataset, window, band_map)
            bands_data = dataset.read(window=window).astype(np.float32)

            quality_mask, quality_summary = _quality_mask(bands_data, rgb_patch, band_map, sensor, dataset.nodata)
            patch_clear = float(quality_mask.mean())
            patch_cloud = float(1.0 - patch_clear)
            patch_valid = float(valid_pixel_fraction(bands_data, dataset.nodata))
            patch_sharp = float(sharpness_score(rgb_patch.mean(axis=-1)))
            patch_quality = float(overall_quality_score(patch_cloud, patch_valid, patch_sharp))

            if patch_clear < MIN_USABLE_FRACTION and "sar" not in sensor.lower():
                discarded += 1
                continue

            radiometric_stats = {
                "band_means": bands_data.mean(axis=(1, 2)).round(6).tolist(),
                "band_stds": bands_data.std(axis=(1, 2)).round(6).tolist(),
            }
            indices = compute_spectral_indices(
                bands_data,
                {k: v - 1 for k, v in band_map.items() if v <= bands_data.shape[0]}
            )
            spectral_indices = {
                "ndvi_mean": float(indices.ndvi.mean()),
                "ndvi_std": float(indices.ndvi.std()),
                "ndwi_mean": float(indices.ndwi.mean()),
                "ndwi_std": float(indices.ndwi.std()),
                "ndbi_mean": float(indices.ndbi.mean()),
                "ndbi_std": float(indices.ndbi.std()),
            }

            img = Image.fromarray((rgb_patch * 255).astype(np.uint8))
            thumb_path = tile_dir / f"subtile_{region_key}_{row}_{col}.png"
            img.save(thumb_path)

            npz_path = tile_dir / f"subtile_{region_key}_{row}_{col}.npz"
            np_band_map = {k: v - 1 for k, v in band_map.items() if v <= bands_data.shape[0]}
            np.savez_compressed(
                npz_path,
                bands=bands_data,
                band_map=np_band_map,
                quality_mask=quality_mask.astype(np.uint8),
                ndvi=indices.ndvi.astype(np.float32),
                ndwi=indices.ndwi.astype(np.float32),
                ndbi=indices.ndbi.astype(np.float32),
            )

            min_lon_t, min_lat_t, max_lon_t, max_lat_t, center_lon, center_lat = _compute_tile_bounds_wgs84(
                dataset, col, row, tile_w, tile_h
            )
            tile_geom = box(min_lon_t, min_lat_t, max_lon_t, max_lat_t)

            emb = embedding_service.embed_image(img.convert("RGB"))
            geo_info = offline_geocoder.reverse_geocode(center_lon, center_lat)

            provenance_payload = {
                "region_key": region_key,
                "region_name": region_info["name"],
                "zone": region_info["zone"],
                "is_fine_grain": True,
                "nearest_landmark": geo_info["name"],
                "nearest_zone": geo_info["zone"],
                "landmark_subtitle": geo_info["subtitle"],
                "distance_to_landmark_km": geo_info["distance_km"],
                "source_scene": scene.source_filename,
            }

            tile_record = Tile(
                tile_id=subtile_id,
                scene_id=scene.scene_id,
                row_off=row,
                col_off=col,
                tile_size=TILE_SIZE,
                lon=center_lon,
                lat=center_lat,
                geometry=safe_from_shape(tile_geom, srid=4326),
                acquisition_date=scene.acquisition_date,
                sensor=sensor,
                resolution_m=scene.resolution_m or 10.0,
                crs=str(crs),
                cloud_fraction=patch_cloud,
                quality_score=patch_quality,
                thumbnail_path=str(thumb_path),
                tile_path=str(thumb_path),
                embedding=emb.vector.tolist(),
                embedding_model=emb.model_name,
                embedding_is_placeholder=bool(emb.is_placeholder),
                embedding_model_version=emb.model_version,
                processing_version=settings.PROCESSING_VERSION,
                clear_fraction=patch_clear,
                quality_mask_summary=quality_summary,
                radiometric_stats=radiometric_stats,
                spectral_indices=spectral_indices,
                provenance=provenance_payload,
            )
            session.add(tile_record)

            # Upsert into Qdrant (appends without deleting any existing vectors)
            vector_store.upsert_tile(
                tile_id=subtile_id,
                vector=emb.vector.tolist(),
                sensor=sensor,
                acquisition_date=scene.acquisition_date.isoformat() if scene.acquisition_date else None,
                lon=center_lon,
                lat=center_lat,
                extra_payload={
                    "scene_id": str(scene.scene_id),
                    "quality_score": patch_quality,
                    "cloud_fraction": patch_cloud,
                    "thumbnail_path": str(thumb_path),
                    "embedding_is_placeholder": bool(emb.is_placeholder),
                    "embedding_model_version": emb.model_version,
                    "clear_fraction": patch_clear,
                    "quality_mask_summary": quality_summary,
                    "radiometric_stats": radiometric_stats,
                    "spectral_indices": spectral_indices,
                    "region_key": region_key,
                    "region_name": region_info["name"],
                    "zone": region_info["zone"],
                    "is_fine_grain": True,
                    "nearest_landmark": geo_info["name"],
                    "landmark_subtitle": geo_info["subtitle"],
                },
            )
            created += 1

    return {"created": created, "skipped": skipped, "discarded": discarded}


def run():
    print("=" * 70)
    print("TerreX Regional Dense Sub-Tiling & Embedding Generation")
    print("Targets: Salt Lake Sector 5, New Town / Rajarhat, Howrah (central)")
    print("Qdrant: Appending new sub-tile vectors (existing vectors untouched)")
    print("=" * 70)

    initial_qdrant_count = vector_store.count()
    print(f"\nInitial Qdrant vector count: {initial_qdrant_count}")

    with get_session() as session:
        scenes = session.execute(select(Scene).where(Scene.status == "ingested")).scalars().all()
        print(f"Found {len(scenes)} ingested scenes to process.\n")

        total_created = 0
        total_skipped = 0

        for scene in scenes:
            scene_path = Path(scene.source_path)
            if not scene_path.exists():
                # Fallback check in SCENES_DIR
                scene_path = settings.SCENES_DIR / scene.source_filename
            if not scene_path.exists():
                logger.warning("Raster file missing for scene %s: %s", scene.scene_id, scene.source_path)
                continue

            print(f"-- Processing Scene: {scene.source_filename[:45]}... [{scene.acquisition_date.strftime('%Y-%m-%d') if scene.acquisition_date else 'N/A'}]")
            with rasterio.open(scene_path) as ds:
                for rkey, rinfo in REGION_METADATA.items():
                    res = generate_subtiles_for_region(
                        dataset=ds,
                        scene=scene,
                        region_key=rkey,
                        region_info=rinfo,
                        session=session,
                    )
                    total_created += res["created"]
                    total_skipped += res["skipped"]
                    print(f"   [{rinfo['name']:22s}] -> Created: {res['created']:3d} | Skipped: {res['skipped']:3d} | Discarded: {res['discarded']:3d}")

            session.commit()

    final_qdrant_count = vector_store.count()
    print("\n" + "=" * 70)
    print(f"SUB-TILING COMPLETE:")
    print(f"  New fine-grained tiles created : {total_created}")
    print(f"  Existing tiles preserved      : {total_skipped}")
    print(f"  Initial Qdrant vectors        : {initial_qdrant_count}")
    print(f"  Final Qdrant vectors          : {final_qdrant_count} (+{final_qdrant_count - initial_qdrant_count})")
    print("=" * 70)


if __name__ == "__main__":
    run()
