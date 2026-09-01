"""
Feature 1 — Satellite image ingestion pipeline.

GeoTIFF / COG -> read metadata -> validate CRS/dimensions -> quality check
-> tile -> embed -> store in Qdrant + PostgreSQL/PostGIS.

Designed to be run per-file so new imagery dropped into data/incoming/ can
be processed independently and merged into the existing index without a
full rebuild (see scripts/ingest.py).
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform_bounds
from shapely.geometry import box, mapping
from geoalchemy2.shape import from_shape

from config import settings
from db.database import get_session
from db.models import Scene, Tile
from services.embeddings import embedding_service
from services.vector_store import vector_store
from services.quality import (
    cloud_fraction_estimate, valid_pixel_fraction, sharpness_score, overall_quality_score
)

logger = logging.getLogger("terrex.ingestion")

MIN_DIMENSION = 64  # reject scenes smaller than this in either axis


class IngestionError(Exception):
    pass


def _read_rgb_float(dataset: rasterio.DatasetReader, window=None) -> np.ndarray:
    """Read up to first 3 bands as float [0,1] HWC array for quality/embedding use."""
    band_count = min(dataset.count, 3)
    arr = dataset.read(indexes=list(range(1, band_count + 1)), window=window).astype(np.float32)
    if arr.shape[0] < 3:
        arr = np.repeat(arr[:1], 3, axis=0)
    # robust per-band normalisation (2nd/98th percentile) instead of assuming 8-bit
    out = np.zeros_like(arr)
    for i in range(3):
        band = arr[i]
        lo, hi = np.percentile(band, [2, 98])
        if hi - lo < 1e-6:
            hi = lo + 1.0
        out[i] = np.clip((band - lo) / (hi - lo), 0, 1)
    return np.transpose(out, (1, 2, 0))  # HWC


def _extract_sensor_and_date(dataset: rasterio.DatasetReader, filename: str) -> tuple:
    """
    Best-effort metadata extraction. Real pipelines would parse sensor-specific
    XML/JSON sidecars; for the MVP we check GDAL tags and fall back to
    filename conventions like SENSOR_YYYYMMDD_*.tif
    """
    tags = dataset.tags()
    sensor = tags.get("SENSOR") or tags.get("SATELLITE") or None
    date_str = tags.get("ACQUISITION_DATE") or tags.get("TIFFTAG_DATETIME")
    acq_date = None
    if date_str:
        for fmt in ("%Y-%m-%d", "%Y:%m:%d %H:%M:%S", "%Y%m%d"):
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
        raise IngestionError("Missing CRS")
    if dataset.width < MIN_DIMENSION or dataset.height < MIN_DIMENSION:
        raise IngestionError(f"Dimensions too small: {dataset.width}x{dataset.height}")
    if dataset.count < 1:
        raise IngestionError("No raster bands present")


def ingest_file(path: Path, move_to_scenes: bool = True) -> dict:
    """
    Ingest a single GeoTIFF/COG file end-to-end. Returns a summary dict.
    Raises IngestionError on validation failure (scene is still recorded
    with status='quarantined' so provenance of the failed attempt is kept).
    """
    logger.info("Ingesting %s", path)
    with rasterio.open(path) as dataset:
        try:
            validate_dataset(dataset)
        except IngestionError as exc:
            _record_quarantine(path, str(exc))
            raise

        rgb = _read_rgb_float(dataset)
        cloud_frac = cloud_fraction_estimate(rgb)
        valid_frac = valid_pixel_fraction(dataset.read())
        sharp = sharpness_score(rgb.mean(axis=-1))
        quality = overall_quality_score(cloud_frac, valid_frac, sharp)

        sensor, acq_date = _extract_sensor_and_date(dataset, path.name)
        bounds_wgs84 = transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds)
        footprint = box(*bounds_wgs84)

        resolution_m = abs(dataset.transform.a)

        scene_id = None
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
                width=dataset.width,
                height=dataset.height,
                band_count=dataset.count,
                cloud_fraction=cloud_frac,
                quality_score=quality,
                valid_pixel_fraction=valid_frac,
                footprint=from_shape(footprint, srid=4326),
                processing_version=settings.PROCESSING_VERSION,
                status="ingested",
            )
            session.add(scene)
            session.flush()
            scene_id = scene.scene_id

            tiles_created = _tile_and_index(dataset, scene, session, rgb_full=rgb, bounds_wgs84=bounds_wgs84)

        logger.info("Ingested scene %s with %d tiles", scene_id, tiles_created)
        return {
            "scene_id": scene_id,
            "tiles": tiles_created,
            "quality_score": quality,
            "cloud_fraction": cloud_frac,
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


def _tile_and_index(dataset, scene: Scene, session, rgb_full: np.ndarray, bounds_wgs84) -> int:
    """Cut the scene into tiles, embed each, push to Qdrant + Postgres."""
    ts = settings.TILE_SIZE
    h, w = dataset.height, dataset.width
    min_lon, min_lat, max_lon, max_lat = bounds_wgs84
    lon_span = max_lon - min_lon
    lat_span = max_lat - min_lat

    count = 0
    tile_dir = settings.TILES_DIR / scene.scene_id
    tile_dir.mkdir(parents=True, exist_ok=True)

    for row in range(0, h - ts + 1, ts) or [0]:
        for col in range(0, w - ts + 1, ts) or [0]:
            row_end = min(row + ts, h)
            col_end = min(col + ts, w)
            patch = rgb_full[row:row_end, col:col_end, :]
            if patch.shape[0] < ts // 2 or patch.shape[1] < ts // 2:
                continue  # skip slivers at the edge

            patch_cloud = cloud_fraction_estimate(patch)
            patch_quality = overall_quality_score(
                patch_cloud,
                valid_pixel_fraction(np.transpose(patch, (2, 0, 1))),
                sharpness_score(patch.mean(axis=-1)),
            )

            img = Image.fromarray((patch * 255).astype(np.uint8))
            tile_path = tile_dir / f"tile_{row}_{col}.png"
            img.save(tile_path)

            emb = embedding_service.embed_image(img)

            # approximate geo bounds of this tile via linear interpolation
            tlon0 = min_lon + lon_span * (col / w)
            tlon1 = min_lon + lon_span * (col_end / w)
            tlat0 = max_lat - lat_span * (row_end / h)
            tlat1 = max_lat - lat_span * (row / h)
            tile_poly = box(tlon0, tlat0, tlon1, tlat1)
            center_lon = (tlon0 + tlon1) / 2
            center_lat = (tlat0 + tlat1) / 2

            tile = Tile(
                scene_id=scene.scene_id,
                row_off=row,
                col_off=col,
                tile_size=ts,
                lon=center_lon,
                lat=center_lat,
                geometry=from_shape(tile_poly, srid=4326),
                acquisition_date=scene.acquisition_date,
                sensor=scene.sensor,
                resolution_m=scene.resolution_m,
                crs=scene.crs,
                cloud_fraction=patch_cloud,
                quality_score=patch_quality,
                thumbnail_path=str(tile_path),
                tile_path=str(tile_path),
                embedding_model=emb.model_name,
                embedding_is_placeholder=emb.is_placeholder,
                processing_version=settings.PROCESSING_VERSION,
            )
            session.add(tile)
            session.flush()

            vector_store.upsert_tile(
                tile_id=tile.tile_id,
                vector=emb.vector,
                payload={
                    "scene_id": scene.scene_id,
                    "lon": center_lon,
                    "lat": center_lat,
                    "sensor": scene.sensor,
                    "acquisition_date": scene.acquisition_date.isoformat() if scene.acquisition_date else None,
                    "quality_score": patch_quality,
                    "cloud_fraction": patch_cloud,
                    "thumbnail_path": str(tile_path),
                    "embedding_is_placeholder": emb.is_placeholder,
                },
            )
            count += 1
    return count
