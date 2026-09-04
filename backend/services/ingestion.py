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
import hashlib
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, Tuple

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
MIN_USABLE_FRACTION = 0.20

# Sensor band mappings (1-based band indexes for rasterio)
DEFAULT_BAND_MAPS: Dict[str, Dict[str, int]] = {
    "sentinel-2": {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5, "swir2": 6, "scl": 7},
    "sentinel2": {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5, "swir2": 6, "scl": 7},
    "landsat-8": {"blue": 2, "green": 3, "red": 4, "nir": 5, "swir1": 6},
    "landsat": {"blue": 2, "green": 3, "red": 4, "nir": 5, "swir1": 6},
    "rgb": {"red": 1, "green": 2, "blue": 3},
    "bgr": {"blue": 1, "green": 2, "red": 3},
}


class IngestionError(Exception):
    pass


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def _deterministic_tile_id(scene_key: str, row: int, col: int, acquisition_date: Optional[datetime]) -> str:
    key = f"{scene_key}|{row}|{col}|{acquisition_date.isoformat() if acquisition_date else ''}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _quality_mask(
    bands_data: np.ndarray,
    rgb_patch: np.ndarray,
    band_map: Dict[str, int],
    sensor: str,
    nodata_value=None,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Return a per-pixel usable mask and explainable quality diagnostics."""
    valid = np.isfinite(bands_data).all(axis=0)
    if nodata_value is not None:
        valid &= ~np.all(bands_data == nodata_value, axis=0)
    else:
        valid &= ~np.all(bands_data == 0, axis=0)

    sensor_lower = sensor.lower()
    if "sar" in sensor_lower or "sentinel-1" in sensor_lower or "sentinel1" in sensor_lower:
        backscatter = bands_data[0]
        finite = np.isfinite(backscatter) & (backscatter != 0)
        mean = float(np.abs(backscatter[finite]).mean()) if finite.any() else 0.0
        std = float(np.abs(backscatter[finite]).std()) if finite.any() else 0.0
        speckle_cv = std / (mean + 1e-6)
        quality = float(np.clip(1.0 - speckle_cv / 2.0, 0.0, 1.0))
        return valid & finite, {
            "clear_fraction": float((valid & finite).mean()),
            "confounds": [] if quality >= 0.25 else ["speckle"],
            "modality": "sar",
            "speckle_coefficient": round(speckle_cv, 5),
            "speckle_quality": round(quality, 5),
        }

    scl_index = band_map.get("scl")
    if scl_index is not None and 1 <= scl_index <= bands_data.shape[0]:
        scl_index -= 1
        scl = bands_data[scl_index]
        clear = np.isin(scl.astype(np.int32), [4, 5, 6, 7])
        confound_codes = {0: "nodata", 1: "saturated", 2: "dark", 3: "cloud_shadow", 8: "cloud_medium", 9: "cloud_high", 10: "cirrus", 11: "snow"}
        confounds = sorted({name for code, name in confound_codes.items() if np.any(scl.astype(np.int32) == code)})
        mask = valid & clear
        return mask, {"clear_fraction": float(mask.mean()), "confounds": confounds, "modality": "optical", "method": "scl"}

    maxc = rgb_patch.max(axis=-1)
    minc = rgb_patch.min(axis=-1)
    brightness = rgb_patch.mean(axis=-1)
    saturation = (maxc - minc) / (maxc + 1e-6)
    cloud_like = (brightness > 0.75) & (saturation < 0.15)
    mask = valid & ~cloud_like
    confounds = ["cloud_haze"] if cloud_like.any() else []
    return mask, {"clear_fraction": float(mask.mean()), "confounds": confounds, "modality": "optical", "method": "brightness_saturation"}


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

    if dataset.count >= 7:
        return {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5, "swir2": 6, "scl": 7}
    if dataset.count >= 6:
        return {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5, "swir2": 6}
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


def _validate_cog_artifact(path: Path) -> Dict[str, Any]:
    """Validate retained GeoTIFF tiling/overviews without requiring network access."""
    try:
        with rasterio.open(path) as dataset:
            tiled = bool(dataset.profile.get("tiled", False))
            overviews = dataset.overviews(1) if dataset.count else []
            return {"is_tiled": tiled, "overview_levels": overviews, "cog_ready": tiled and bool(overviews)}
    except Exception as exc:
        return {"is_tiled": False, "overview_levels": [], "cog_ready": False, "error": str(exc)}


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
    started = time.perf_counter()
    source_hash = _file_sha256(path)
    with get_session() as existing_session:
        existing_scene = existing_session.query(Scene).filter(Scene.source_hash == source_hash).first()
        if existing_scene and existing_scene.status == "ingested":
            tile_count = len(existing_scene.tiles)
            logger.info("Skipping already indexed scene %s (%d tiles)", path.name, tile_count)
            return {"scene_id": existing_scene.scene_id, "tiles": tile_count, "created_tiles": 0, "skipped_tiles": tile_count, "discarded_tiles": 0, "status": "skipped", "source_hash": source_hash, "elapsed_seconds": round(time.perf_counter() - started, 3)}
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
        cog_info = _validate_cog_artifact(final_path)
        if not cog_info["cog_ready"]:
            logger.warning("Retained scene %s is not fully COG-structured: %s", final_path.name, cog_info)

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
                source_hash=source_hash,
                license_source="unknown",
                cog_validation=cog_info,
            )
            session.add(scene)
            session.flush()
            scene_id = scene.scene_id

            metrics = _tile_and_index_windowed(
                dataset=dataset,
                scene=scene,
                session=session,
                band_map=band_map,
            )

            # Update scene-level aggregated quality
            scene.cloud_fraction = float(metrics["avg_cloud"])
            scene.quality_score = float(metrics["avg_quality"])
            session.flush()

        logger.info("Ingested scene %s (%d tiles, avg_quality=%.2f)", scene_id, metrics["created_tiles"], metrics["avg_quality"])
        return {
            "scene_id": scene_id,
            "tiles": metrics["created_tiles"], "created_tiles": metrics["created_tiles"], "skipped_tiles": metrics["skipped_tiles"], "discarded_tiles": metrics["discarded_tiles"], "discard_reasons": metrics["discard_reasons"],
            "quality_score": round(float(metrics["avg_quality"]), 3),
            "cloud_fraction": round(float(metrics["avg_cloud"]), 3),
            "sensor": sensor,
            "acquisition_date": acq_date.isoformat() if acq_date else None,
            "embedding_model": embedding_service._placeholder.model_name
            if embedding_service.is_placeholder else "remoteclip",
            "embedding_is_placeholder": embedding_service.is_placeholder,
            "embedding_model_version": embedding_service.model_version,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "index_size": vector_store.count(),
            "storage_bytes": _directory_size(settings.SCENES_DIR) + _directory_size(settings.TILES_DIR),
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
) -> dict:
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
    skipped = 0
    discarded = 0
    discard_reasons: Dict[str, int] = {}
    total_cloud = 0.0
    total_quality = 0.0

    for row in range(0, dataset.height, step):
        for col in range(0, dataset.width, step):
            tile_w = min(ts, dataset.width - col)
            tile_h = min(ts, dataset.height - row)
            if tile_h < ts // 2 or tile_w < ts // 2:
                continue  # skip boundary slivers

            window = Window(col_off=col, row_off=row, width=tile_w, height=tile_h)
            deterministic_id = _deterministic_tile_id(str(scene.source_hash or scene.scene_id), row, col, scene.acquisition_date)
            if session.get(Tile, deterministic_id):
                skipped += 1
                continue

            # 1. Read windowed RGB patch for thumbnail & quality
            rgb_patch = _read_tile_rgb_float(dataset, window, band_map)

            # 2. Read full windowed bands for multi-spectral analysis
            bands_data = dataset.read(window=window).astype(np.float32)

            quality_mask, quality_summary = _quality_mask(bands_data, rgb_patch, band_map, scene.sensor or "", dataset.nodata)
            patch_clear = float(quality_mask.mean())
            patch_cloud = float(1.0 - patch_clear)
            patch_valid = float(valid_pixel_fraction(bands_data, dataset.nodata))
            patch_sharp = float(sharpness_score(rgb_patch.mean(axis=-1)))
            patch_quality = float(overall_quality_score(patch_cloud, patch_valid, patch_sharp))
            if patch_clear < MIN_USABLE_FRACTION:
                discarded += 1
                for reason in quality_summary.get("confounds", ["low_clear_fraction"]):
                    discard_reasons[reason] = discard_reasons.get(reason, 0) + 1
                continue

            radiometric_stats = {"band_means": bands_data.mean(axis=(1, 2)).round(6).tolist(), "band_stds": bands_data.std(axis=(1, 2)).round(6).tolist()}
            indices = compute_spectral_indices(bands_data, {k: v - 1 for k, v in band_map.items() if v <= bands_data.shape[0]})
            spectral_indices = {"ndvi_mean": float(indices.ndvi.mean()), "ndvi_std": float(indices.ndvi.std()), "ndwi_mean": float(indices.ndwi.mean()), "ndwi_std": float(indices.ndwi.std()), "ndbi_mean": float(indices.ndbi.mean()), "ndbi_std": float(indices.ndbi.std())}

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
                quality_mask=quality_mask.astype(np.uint8),
                ndvi=indices.ndvi.astype(np.float32),
                ndwi=indices.ndwi.astype(np.float32),
                ndbi=indices.ndbi.astype(np.float32),
            )

            # 5. Accurate geospatial bounding box
            min_lon, min_lat, max_lon, max_lat, center_lon, center_lat = _compute_tile_bounds_wgs84(
                dataset, col, row, tile_w, tile_h
            )
            tile_poly = box(min_lon, min_lat, max_lon, max_lat)

            # 6. Generate embedding
            emb = embedding_service.embed_image(img)

            tile = Tile(
                tile_id=deterministic_id,
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
                quality_mask_path=str(npz_path),
                clear_fraction=patch_clear,
                quality_mask_summary=quality_summary,
                radiometric_stats=radiometric_stats,
                spectral_indices=spectral_indices,
                provenance={"source_scene_id": str(scene.scene_id), "source_filename": scene.source_filename, "acquisition_timestamp": scene.acquisition_date.isoformat() if scene.acquisition_date else None, "crs": scene.crs, "footprint_geometry": tile_poly.wkt, "quality_mask_summary": quality_summary, "radiometric_stats": radiometric_stats, "processing_steps": [{"step": "windowed_tiling", "params": {"size": ts}}, {"step": "quality_masking", "method": quality_summary.get("method", "heuristic")}, {"step": "embedding", "model": emb.model_name, "model_version": emb.model_version}], "ingest_timestamp": datetime.utcnow().isoformat(), "license_source": scene.license_source},
                thumbnail_path=str(thumb_path),
                tile_path=str(thumb_path),
                embedding_model=emb.model_name,
                embedding_is_placeholder=bool(emb.is_placeholder),
                embedding_model_version=emb.model_version,
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
                    "embedding_model_version": emb.model_version,
                    "clear_fraction": patch_clear,
                    "quality_mask_summary": quality_summary,
                    "radiometric_stats": radiometric_stats,
                    "spectral_indices": spectral_indices,
                },
            )

            count += 1
            total_cloud += patch_cloud
            total_quality += patch_quality

    avg_cloud = total_cloud / max(count, 1)
    avg_quality = total_quality / max(count, 1)
    return {"created_tiles": count, "skipped_tiles": skipped, "discarded_tiles": discarded, "discard_reasons": discard_reasons, "avg_cloud": float(avg_cloud), "avg_quality": float(avg_quality)}
