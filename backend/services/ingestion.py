"""
Feature 1 — Satellite image ingestion pipeline (Windowed Multispectral).

GeoTIFF / COG -> validate CRS/dimensions -> stream windowed reads per tile
-> quality check -> spectral index derivation -> tile thumbnail & multispectral save
-> embed -> store in Qdrant + PostgreSQL/PostGIS.

Streams tile-by-tile via rasterio.windows.Window so peak RAM consumption is
a function of tile size (e.g. 256x256), NOT scene size (e.g. 10980x10980).
Supports true incremental upsert for newly acquired imagery.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple

import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.warp import transform_bounds, transform
from PIL import Image
from shapely.geometry import box
from geoalchemy2.shape import from_shape

from config import settings
from db.database import get_session
from db.models import Scene, Tile
from services.embeddings import embedding_service
from services.vector_store import vector_store
from services.quality import (
    cloud_fraction_estimate, valid_pixel_fraction, sharpness_score, overall_quality_score
)
from services.algorithms.spectral import compute_spectral_indices

logger = logging.getLogger("terrex.ingestion")

MIN_DIMENSION = 64  # reject scenes smaller than this in either axis

# Sensor band mappings (1-based band indexes for rasterio)
DEFAULT_BAND_MAPS: Dict[str, Dict[str, int]] = {
    "sentinel-2": {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5, "scl": 6},
    "sentinel2": {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5, "scl": 6},
    "landsat-8": {"blue": 2, "green": 3, "red": 4, "nir": 5, "swir1": 6},
    "landsat": {"blue": 2, "green": 3, "red": 4, "nir": 5, "swir1": 6},
    "rgb": {"red": 1, "green": 2, "blue": 3},
    "bgr": {"blue": 1, "green": 2, "red": 3},
}


class IngestionError(Exception):
    pass


def _resolve_band_map(dataset: rasterio.DatasetReader, sensor_name: str) -> Dict[str, int]:
    """Detect band mapping based on metadata tags, descriptions, or sensor profile."""
    tags = dataset.tags()
    band_names_tag = tags.get("BAND_NAMES")
    if band_names_tag:
        names = [b.strip().lower() for b in band_names_tag.split(",")]
        mapping = {}
        for idx, name in enumerate(names, start=1):
            mapping[name] = idx
        return mapping

    # Check descriptions
    descriptions = dataset.descriptions
    if descriptions and any(descriptions):
        mapping = {}
        for idx, desc in enumerate(descriptions, start=1):
            if desc:
                d_lower = desc.lower()
                for key in ("blue", "green", "red", "nir", "swir1", "swir2", "scl"):
                    if key in d_lower:
                        mapping[key] = idx
        if len(mapping) >= 3:
            return mapping

    # Fallback to sensor lookup or channel count defaults
    s_clean = sensor_name.lower().replace(" ", "").replace("_", "-")
    for known_sensor, bmap in DEFAULT_BAND_MAPS.items():
        if known_sensor in s_clean:
            # Verify dataset has enough bands
            if all(v <= dataset.count for v in bmap.values()):
                return bmap

    if dataset.count >= 6:
        return {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5, "scl": 6}
    elif dataset.count >= 4:
        return {"blue": 1, "green": 2, "red": 3, "nir": 4}
    elif dataset.count == 3:
        return {"red": 1, "green": 2, "blue": 3}
    elif dataset.count == 1:
        return {"red": 1, "green": 1, "blue": 1}
    return {"red": 1, "green": min(2, dataset.count), "blue": min(3, dataset.count)}


def _extract_sensor_and_date(dataset: rasterio.DatasetReader, filename: str) -> tuple[str, Optional[datetime]]:
    """Extract sensor name and acquisition date from GDAL tags or filename conventions."""
    tags = dataset.tags()
    sensor = tags.get("SENSOR") or tags.get("SATELLITE") or tags.get("PLATFORM") or None
    date_str = tags.get("ACQUISITION_DATE") or tags.get("TIFFTAG_DATETIME") or tags.get("DATETIME")
    acq_date = None
    if date_str:
        for fmt in ("%Y-%m-%d", "%Y:%m:%d %H:%M:%S", "%Y%m%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                acq_date = datetime.strptime(date_str[:19], fmt)
                break
            except ValueError:
                continue

    stem_parts = Path(filename).stem.split("_")
    if sensor is None and stem_parts:
        sensor = stem_parts[0]
    if acq_date is None:
        for part in stem_parts:
            if part.isdigit() and len(part) == 8:
                try:
                    acq_date = datetime.strptime(part, "%Y%m%d")
                    break
                except ValueError:
                    pass
    return sensor or "unknown", acq_date


def validate_dataset(dataset: rasterio.DatasetReader):
    if dataset.crs is None:
        raise IngestionError("Missing CRS (Coordinate Reference System)")
    if dataset.width < MIN_DIMENSION or dataset.height < MIN_DIMENSION:
        raise IngestionError(f"Dimensions too small: {dataset.width}x{dataset.height}")
    if dataset.count < 1:
        raise IngestionError("No raster bands present in file")


def _read_tile_rgb_float(
    dataset: rasterio.DatasetReader,
    window: Window,
    band_map: Dict[str, int],
) -> np.ndarray:
    """Read a windowed patch as float [0,1] HWC RGB array."""
    r_idx = band_map.get("red", 1)
    g_idx = band_map.get("green", min(2, dataset.count))
    b_idx = band_map.get("blue", min(3, dataset.count))

    r = dataset.read(r_idx, window=window).astype(np.float32)
    g = dataset.read(g_idx, window=window).astype(np.float32)
    b = dataset.read(b_idx, window=window).astype(np.float32)

    stack = np.stack([r, g, b], axis=0)  # (3, H, W)
    lo, hi = np.percentile(stack, [2, 98])
    if hi - lo < 1e-6:
        hi = lo + 1.0
    out = np.clip((stack - lo) / (hi - lo), 0.0, 1.0)
    return np.transpose(out, (1, 2, 0))  # (H, W, 3)


def _compute_tile_bounds_wgs84(
    dataset: rasterio.DatasetReader,
    col_off: int,
    row_off: int,
    width: int,
    height: int,
) -> Tuple[float, float, float, float, float, float]:
    """Derive exact WGS84 tile bounding box and center coordinate from dataset transform."""
    transform_mat = dataset.transform
    # Top-left and bottom-right in dataset native CRS
    x0, y0 = rasterio.transform.xy(transform_mat, row_off, col_off, offset="ul")
    x1, y1 = rasterio.transform.xy(transform_mat, row_off + height, col_off + width, offset="lr")

    min_x, max_x = min(x0, x1), max(x0, x1)
    min_y, max_y = min(y0, y1), max(y0, y1)

    if dataset.crs.to_string() == "EPSG:4326":
        min_lon, min_lat, max_lon, max_lat = min_x, min_y, max_x, max_y
    else:
        min_lon, min_lat, max_lon, max_lat = transform_bounds(
            dataset.crs, "EPSG:4326", min_x, min_y, max_x, max_y
        )
    center_lon = (float(min_lon) + float(max_lon)) / 2.0
    center_lat = (float(min_lat) + float(max_lat)) / 2.0
    return float(min_lon), float(min_lat), float(max_lon), float(max_lat), float(center_lon), float(center_lat)


def ingest_file(path: Path, move_to_scenes: bool = True) -> dict:
    """
    Ingest a single GeoTIFF/COG file end-to-end with streaming windowed reads.
    Returns a summary dict. Quarantines invalid scenes for full auditability.
    """
    logger.info("Ingesting %s", path)
    with rasterio.open(path) as dataset:
        try:
            validate_dataset(dataset)
        except IngestionError as exc:
            _record_quarantine(path, str(exc))
            raise

        sensor, acq_date = _extract_sensor_and_date(dataset, path.name)
        band_map = _resolve_band_map(dataset, sensor)
        bounds_wgs84 = transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds)
        footprint = box(*bounds_wgs84)
        resolution_m = float(abs(dataset.transform.a))

        final_path = path
        if move_to_scenes:
            final_path = settings.SCENES_DIR / path.name
            if final_path != path:
                shutil.copy2(path, final_path)

        with get_session() as session:
            scene = Scene(
                source_filename=path.name,
                source_path=str(final_path),
                sensor=sensor,
                acquisition_date=acq_date,
                resolution_m=resolution_m,
                crs=str(dataset.crs),
                width=int(dataset.width),
                height=int(dataset.height),
                band_count=int(dataset.count),
                cloud_fraction=0.0,
                quality_score=1.0,
                valid_pixel_fraction=1.0,
                footprint=from_shape(footprint, srid=4326),
                processing_version=settings.PROCESSING_VERSION,
                status="ingested",
            )
            session.add(scene)
            session.flush()
            scene_id = scene.scene_id

            tiles_created, avg_cloud, avg_quality = _tile_and_index_windowed(
                dataset=dataset,
                scene=scene,
                session=session,
                band_map=band_map,
            )

            # Update scene-level aggregated quality
            scene.cloud_fraction = float(avg_cloud)
            scene.quality_score = float(avg_quality)
            session.flush()

        logger.info("Ingested scene %s (%d tiles, avg_quality=%.2f)", scene_id, tiles_created, avg_quality)
        return {
            "scene_id": scene_id,
            "tiles": tiles_created,
            "quality_score": round(float(avg_quality), 3),
            "cloud_fraction": round(float(avg_cloud), 3),
            "sensor": sensor,
            "acquisition_date": acq_date.isoformat() if acq_date else None,
            "embedding_model": embedding_service._placeholder.model_name
            if embedding_service.is_placeholder else "remoteclip",
            "embedding_is_placeholder": embedding_service.is_placeholder,
        }


def _record_quarantine(path: Path, reason: str):
    with get_session() as session:
        session.add(Scene(
            source_filename=path.name,
            source_path=str(path),
            processing_version=settings.PROCESSING_VERSION,
            status="quarantined",
            status_reason=reason,
        ))
    logger.warning("Quarantined %s: %s", path, reason)


def _tile_and_index_windowed(
    dataset: rasterio.DatasetReader,
    scene: Scene,
    session,
    band_map: Dict[str, int],
) -> Tuple[int, float, float]:
    """
    Stream windowed chunks through memory, compute multispectral derivatives,
    save thumbnail/pack, embed, and index in PostGIS + Qdrant.
    Peak memory is bounded to tile_size x tile_size x bands.
    """
    ts = settings.TILE_SIZE
    overlap = settings.TILE_OVERLAP
    step = ts - overlap

    tile_dir = settings.TILES_DIR / str(scene.scene_id)
    tile_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    total_cloud = 0.0
    total_quality = 0.0

    for row in range(0, dataset.height, step):
        for col in range(0, dataset.width, step):
            tile_w = min(ts, dataset.width - col)
            tile_h = min(ts, dataset.height - row)
            if tile_h < ts // 2 or tile_w < ts // 2:
                continue  # skip boundary slivers

            window = Window(col_off=col, row_off=row, width=tile_w, height=tile_h)

            # 1. Read windowed RGB patch for thumbnail & quality
            rgb_patch = _read_tile_rgb_float(dataset, window, band_map)

            # 2. Read full windowed bands for multi-spectral analysis
            bands_data = dataset.read(window=window).astype(np.float32)

            patch_cloud = float(cloud_fraction_estimate(rgb_patch))
            patch_valid = float(valid_pixel_fraction(bands_data))
            patch_sharp = float(sharpness_score(rgb_patch.mean(axis=-1)))
            patch_quality = float(overall_quality_score(patch_cloud, patch_valid, patch_sharp))

            # 3. Save RGB thumbnail
            img = Image.fromarray((rgb_patch * 255).astype(np.uint8))
            thumb_path = tile_dir / f"tile_{row}_{col}.png"
            img.save(thumb_path)

            # 4. Save multi-spectral numpy pack for downstream change typing
            npz_path = tile_dir / f"tile_{row}_{col}.npz"
            # 0-based band map for numpy array indexing
            np_band_map = {k: v - 1 for k, v in band_map.items() if v <= bands_data.shape[0]}
            np.savez_compressed(
                npz_path,
                bands=bands_data,
                band_map=np_band_map,
            )

            # 5. Accurate geospatial bounding box
            min_lon, min_lat, max_lon, max_lat, center_lon, center_lat = _compute_tile_bounds_wgs84(
                dataset, col, row, tile_w, tile_h
            )
            tile_poly = box(min_lon, min_lat, max_lon, max_lat)

            # 6. Generate embedding
            emb = embedding_service.embed_image(img)

            tile = Tile(
                scene_id=str(scene.scene_id),
                row_off=int(row),
                col_off=int(col),
                tile_size=int(max(tile_h, tile_w)),
                lon=float(center_lon),
                lat=float(center_lat),
                geometry=from_shape(tile_poly, srid=4326),
                acquisition_date=scene.acquisition_date,
                sensor=scene.sensor,
                resolution_m=float(scene.resolution_m) if scene.resolution_m is not None else None,
                crs=scene.crs,
                cloud_fraction=float(patch_cloud),
                quality_score=float(patch_quality),
                thumbnail_path=str(thumb_path),
                tile_path=str(thumb_path),
                embedding_model=emb.model_name,
                embedding_is_placeholder=bool(emb.is_placeholder),
                processing_version=settings.PROCESSING_VERSION,
            )
            session.add(tile)
            session.flush()

            # 7. Upsert into Qdrant vector index
            vector_store.upsert_tile(
                tile_id=tile.tile_id,
                vector=emb.vector,
                payload={
                    "scene_id": str(scene.scene_id),
                    "lon": float(center_lon),
                    "lat": float(center_lat),
                    "sensor": scene.sensor,
                    "acquisition_date": scene.acquisition_date.isoformat() if scene.acquisition_date else None,
                    "quality_score": float(patch_quality),
                    "cloud_fraction": float(patch_cloud),
                    "thumbnail_path": str(thumb_path),
                    "embedding_is_placeholder": bool(emb.is_placeholder),
                },
            )

            count += 1
            total_cloud += patch_cloud
            total_quality += patch_quality

    avg_cloud = total_cloud / max(count, 1)
    avg_quality = total_quality / max(count, 1)
    return count, float(avg_cloud), float(avg_quality)
