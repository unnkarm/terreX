"""Dense multi-temporal EO change-point analysis.

Optical and SAR observations are never directly differenced.  Each modality is
registered and normalized against its own median baseline; the resulting bounded
change signals are then interleaved chronologically for persistence analysis.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image
from sqlalchemy import select

from config import settings
from db.database import get_session
from db.models import ChangeResult, Tile
from services.algorithms.change_classifier import classify_change_regions
from services.algorithms.normalization import normalize_histogram_match
from services.algorithms.registration import register_image_pair
from services.algorithms.spectral import compute_spectral_indices
from services.change_detection import (
    _difference_to_change_map,
    _extract_pair_features,
    _load_precomputed_indices,
    _load_tile_multispectral_or_rgb,
    find_candidate_tiles,
)
from services.false_alarm import ObservationQuality, evaluate
from services.quality import cloud_fraction_estimate, sharpness_score, valid_pixel_fraction
from services.time_series_change import PassSignal, detect_change_point


def _assert_operational_aoi(lon: float, lat: float) -> None:
    bounds = (
        settings.KOLKATA_AOI_MIN_LON,
        settings.KOLKATA_AOI_MIN_LAT,
        settings.KOLKATA_AOI_MAX_LON,
        settings.KOLKATA_AOI_MAX_LAT,
    )
    if not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]):
        raise ValueError(
            "Requested coordinate is outside the configured Greater Kolkata / West Bengal "
            f"operational boundary {bounds}. The eastern longitude limit is {bounds[2]:.2f}E."
        )


def _modality(sensor: Optional[str]) -> str:
    value = (sensor or "").lower()
    return "sar" if "sar" in value or "radar" in value or "c-sar" in value else "optical"


def _resize_hwc(array: np.ndarray, height: int, width: int, channels: int) -> np.ndarray:
    source = np.asarray(array, dtype=np.float32)[..., :channels]
    if source.shape[:2] == (height, width):
        return source
    resized = [
        np.asarray(
            Image.fromarray(source[..., channel]).resize((width, height), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
        for channel in range(source.shape[-1])
    ]
    return np.stack(resized, axis=-1)


def _median_baseline(entries: list[dict[str, Any]]) -> tuple[np.ndarray, dict[str, int]]:
    reference = entries[0]
    height, width = reference["raster"].shape[:2]
    channels = min(item["raster"].shape[-1] for item in entries)
    stack = np.stack(
        [_resize_hwc(item["raster"], height, width, channels) for item in entries],
        axis=0,
    )
    band_map = {
        key: int(value)
        for key, value in (reference["band_map"] or {}).items()
        if int(value) < channels
    }
    return np.nanmedian(stack, axis=0).astype(np.float32), band_map


def _quality(tile: Tile, raster: np.ndarray) -> ObservationQuality:
    rgb = raster[..., : min(3, raster.shape[-1])]
    if rgb.shape[-1] == 1:
        rgb = np.repeat(rgb, 3, axis=-1)
    return ObservationQuality(
        cloud_fraction=float(tile.cloud_fraction if tile.cloud_fraction is not None else cloud_fraction_estimate(rgb)),
        valid_pixel_fraction=float(tile.clear_fraction if tile.clear_fraction is not None else valid_pixel_fraction(np.transpose(raster, (2, 0, 1)))),
        sharpness=float(sharpness_score(rgb.mean(axis=-1))),
        quality_score=float(tile.quality_score if tile.quality_score is not None else 0.5),
    )


def _observation_payload(entry: dict[str, Any], index: int) -> dict[str, Any]:
    tile: Tile = entry["tile"]
    indices = entry["indices"]
    thumb_name = Path(tile.thumbnail_path).name if tile.thumbnail_path else ""
    return {
        "index": index + 1,
        "tile_id": str(tile.tile_id),
        "scene_id": str(tile.scene_id),
        "acquisition_date": tile.acquisition_date.isoformat(),
        "date_formatted": tile.acquisition_date.strftime("%Y-%m-%d"),
        "year": tile.acquisition_date.strftime("%Y"),
        "sensor": tile.sensor or "Unknown",
        "modality": entry["modality"],
        "cloud_fraction": round(entry["quality"].cloud_fraction, 4),
        "quality_score": round(entry["quality"].quality_score, 4),
        "valid_pixel_fraction": round(entry["quality"].valid_pixel_fraction, 4),
        "is_valid": bool(entry["valid"]),
        "thumbnail_url": f"/static/tiles/{tile.scene_id}/{thumb_name}" if thumb_name else None,
        "distance_from_baseline": round(float(entry.get("signal", 0.0)), 4),
        "change_signal": round(float(entry.get("signal", 0.0)), 4),
        "mean_ndvi": round(float(indices.ndvi.mean()), 4) if entry["modality"] == "optical" else None,
        "mean_ndwi": round(float(indices.ndwi.mean()), 4) if entry["modality"] == "optical" else None,
        "mean_ndbi": round(float(indices.ndbi.mean()), 4) if entry["modality"] == "optical" else None,
        "d_ndvi": round(float(entry.get("d_ndvi", 0.0)), 4) if entry["modality"] == "optical" else None,
        "d_ndwi": round(float(entry.get("d_ndwi", 0.0)), 4) if entry["modality"] == "optical" else None,
        "d_ndbi": round(float(entry.get("d_ndbi", 0.0)), 4) if entry["modality"] == "optical" else None,
        "registration": entry.get("registration"),
        "radiometric_normalization": entry.get("radiometric_normalization"),
        "is_baseline": False,
        "is_earliest_change": False,
        "is_persistence_confirmation": False,
        "is_transient": False,
    }


def run_dense_change_detection(
    *,
    lon: float,
    lat: float,
    date_from: str,
    date_to: str,
    tile_id: Optional[str] = None,
    baseline_n: Optional[int] = None,
    persistence_k: Optional[int] = None,
    threshold: Optional[float] = None,
) -> dict[str, Any]:
    _assert_operational_aoi(lon, lat)
    baseline_n = settings.CHANGE_BASELINE_OBSERVATIONS if baseline_n is None else baseline_n
    persistence_k = settings.CHANGE_PERSISTENCE_K if persistence_k is None else persistence_k
    threshold = threshold if threshold is not None else settings.CHANGE_POINT_THRESHOLD

    candidates = find_candidate_tiles(
        lon, lat, date_from, date_to, tolerance_deg=0.08, reference_tile_id=tile_id
    )
    if len(candidates) < baseline_n + persistence_k:
        return {
            "status": "insufficient_data",
            "is_fallback": False,
            "result_source": "backend",
            "message": (
                f"Found {len(candidates)} usable observations; dense change-point analysis "
                f"requires at least {baseline_n + persistence_k} ({baseline_n} baseline + "
                f"{persistence_k} persistence passes)."
            ),
            "candidate_count": len(candidates),
            "required_observations": baseline_n + persistence_k,
        }

    with get_session() as session:
        entries: list[dict[str, Any]] = []
        for candidate in candidates:
            tile = session.get(Tile, candidate["tile_id"])
            if tile is None or not tile.acquisition_date:
                continue
            raster, band_map = _load_tile_multispectral_or_rgb(tile)
            modality = _modality(tile.sensor)
            indices = _load_precomputed_indices(tile) or compute_spectral_indices(raster, band_map)
            quality = _quality(tile, raster)
            valid = (
                quality.quality_score >= settings.MIN_QUALITY_SCORE
                and quality.cloud_fraction <= settings.CLOUD_FRACTION_MAX
                and quality.valid_pixel_fraction >= 0.70
            )
            entries.append({
                "tile": tile,
                "raster": raster,
                "band_map": band_map or {},
                "indices": indices,
                "quality": quality,
                "valid": valid,
                "modality": modality,
                "signal": 0.0,
            })

        entries.sort(key=lambda item: item["tile"].acquisition_date)
        valid_indices = [index for index, item in enumerate(entries) if item["valid"]]
        if len(valid_indices) < baseline_n + persistence_k:
            return {
                "status": "insufficient_data",
                "is_fallback": False,
                "result_source": "backend",
                "message": (
                    f"Only {len(valid_indices)} of {len(entries)} observations passed quality gating; "
                    f"{baseline_n + persistence_k} are required."
                ),
                "candidate_count": len(entries),
                "usable_observation_count": len(valid_indices),
            }

        baseline_indices = valid_indices[:baseline_n]
        baseline_end = baseline_indices[-1]
        modality_baselines: dict[str, tuple[np.ndarray, dict[str, int], dict[str, Any]]] = {}
        for modality in {item["modality"] for item in entries}:
            baseline_entries = [
                item for index, item in enumerate(entries)
                if index <= baseline_end and item["valid"] and item["modality"] == modality
            ]
            if not baseline_entries:
                baseline_entries = [item for item in entries if item["valid"] and item["modality"] == modality][:1]
            baseline_raster, baseline_map = _median_baseline(baseline_entries)
            modality_baselines[modality] = (baseline_raster, baseline_map, baseline_entries[-1])

        analysis_by_index: dict[int, dict[str, Any]] = {}
        for index, entry in enumerate(entries):
            baseline_raster, baseline_map, reference_entry = modality_baselines[entry["modality"]]
            height, width, channels = baseline_raster.shape
            current = _resize_hwc(entry["raster"], height, width, channels)
            current_map = {
                key: int(value)
                for key, value in entry["band_map"].items()
                if int(value) < channels
            }
            is_reference = entry is reference_entry
            if index in baseline_indices or is_reference:
                normalized = current
                probability = np.zeros((height // 16 or 1, width // 16 or 1), dtype=np.float32)
                registration_payload = {
                    "is_aligned": True,
                    "correlation_before": 1.0,
                    "correlation_after": 1.0,
                    "inliers": 0,
                    "dx": 0.0,
                    "dy": 0.0,
                    "method": "baseline_reference",
                }
                feature_placeholder = entry["modality"] != "optical"
            else:
                registration = register_image_pair(baseline_raster, current)
                normalized = normalize_histogram_match(registration.aligned_after, baseline_raster)
                before_features, _, after_features, _ = _extract_pair_features(
                    baseline_raster, baseline_map, normalized, current_map
                )
                probability = _difference_to_change_map(before_features.array, after_features.array)
                feature_score = float(np.mean(probability))
                dynamic_range = max(
                    float(np.nanpercentile(baseline_raster, 95) - np.nanpercentile(baseline_raster, 5)),
                    1e-6,
                )
                pixel_score = min(1.0, float(np.median(np.abs(normalized - baseline_raster))) / dynamic_range)

                base_indices = compute_spectral_indices(baseline_raster, baseline_map)
                current_indices = compute_spectral_indices(normalized, current_map)
                if entry["modality"] == "optical":
                    entry["d_ndvi"] = float(current_indices.ndvi.mean() - base_indices.ndvi.mean())
                    entry["d_ndwi"] = float(current_indices.ndwi.mean() - base_indices.ndwi.mean())
                    entry["d_ndbi"] = float(current_indices.ndbi.mean() - base_indices.ndbi.mean())
                    spectral_score = min(
                        1.0,
                        2.0 * np.mean([
                            abs(entry["d_ndvi"]), abs(entry["d_ndwi"]), abs(entry["d_ndbi"])
                        ]),
                    )
                    entry["signal"] = min(1.0, 0.55 * feature_score + 0.30 * spectral_score + 0.15 * pixel_score)
                else:
                    entry["signal"] = min(1.0, 0.70 * feature_score + 0.30 * pixel_score)
                registration_payload = {
                    "is_aligned": bool(registration.is_aligned),
                    "correlation_before": round(registration.correlation_before, 4),
                    "correlation_after": round(registration.correlation_after, 4),
                    "inliers": int(registration.inliers),
                    "dx": round(registration.dx, 3),
                    "dy": round(registration.dy, 3),
                    "method": "orb_ransac" if registration.inliers > 0 else "phase_correlation",
                }
                if not registration_payload["is_aligned"]:
                    entry["valid"] = False
                feature_placeholder = bool(before_features.is_placeholder or after_features.is_placeholder)

            raw_mean_delta = float(abs(current.mean() - baseline_raster.mean()))
            normalized_mean_delta = float(abs(normalized.mean() - baseline_raster.mean()))
            entry["registration"] = registration_payload
            entry["radiometric_normalization"] = {
                "method": "histogram_matching",
                "mean_delta_before": round(raw_mean_delta, 5),
                "mean_delta_after": round(normalized_mean_delta, 5),
                "improved": normalized_mean_delta <= raw_mean_delta + 1e-6,
            }
            entry["feature_is_placeholder"] = feature_placeholder
            analysis_by_index[index] = {
                "probability": probability,
                "normalized": normalized,
                "baseline": baseline_raster,
                "baseline_map": baseline_map,
                "current_map": current_map,
                "registration": registration_payload,
                "reference_entry": reference_entry,
                "feature_is_placeholder": feature_placeholder,
            }

        valid_indices = [index for index, item in enumerate(entries) if item["valid"]]
        pass_signals = [
            PassSignal(
                timestamp=item["tile"].acquisition_date,
                score=float(item["signal"]),
                valid=bool(item["valid"]),
                tile_id=str(item["tile"].tile_id),
                modality=item["modality"],
                quality_score=item["quality"].quality_score,
            )
            for item in entries
        ]
        change_point = detect_change_point(
            pass_signals,
            baseline_n=baseline_n,
            persistence_k=persistence_k,
            threshold=threshold,
        )
        observations = [_observation_payload(item, index) for index, item in enumerate(entries)]
        for index in change_point.baseline_indices:
            observations[index]["is_baseline"] = True
        for index in change_point.transient_indices:
            observations[index]["is_transient"] = True
        if change_point.onset_index is not None:
            observations[change_point.onset_index]["is_earliest_change"] = True
        if change_point.confirmation_index is not None:
            observations[change_point.confirmation_index]["is_persistence_confirmation"] = True

        persistence = {
            "status": change_point.status,
            "baseline_n": baseline_n,
            "persistence_k": persistence_k,
            "threshold": threshold,
            "earliest_supported_observation": change_point.earliest_supported.isoformat() if change_point.earliest_supported else None,
            "confirmed_observation": change_point.confirmed_at.isoformat() if change_point.confirmed_at else None,
            "last_clear_observation": change_point.last_clear_at.isoformat() if change_point.last_clear_at else None,
            "temporal_uncertainty_days": change_point.temporal_uncertainty_days,
            "confirmation_lag_days": change_point.confirmation_lag_days,
            "transient_count": len(change_point.transient_indices),
            "log": change_point.log,
        }

        if not change_point.is_confirmed:
            labels = {
                "transient_only": "Only transient anomalies were observed; none met the persistence rule.",
                "no_change": "No valid observation crossed the change threshold.",
                "insufficient_data": "The usable stack could not establish the requested baseline.",
            }
            return {
                "status": change_point.status,
                "is_fallback": False,
                "result_source": "backend",
                "message": labels.get(change_point.status, "No confirmed change."),
                "observations": observations,
                "persistence": persistence,
                "candidate_count": len(entries),
                "usable_observation_count": len(valid_indices),
            }

        onset_index = int(change_point.onset_index)
        confirmation_index = int(change_point.confirmation_index)
        onset_entry = entries[onset_index]
        confirmation_entry = entries[confirmation_index]
        analysis = analysis_by_index[onset_index]
        reference_entry = analysis["reference_entry"]
        before_tile: Tile = reference_entry["tile"]
        after_tile: Tile = onset_entry["tile"]

        probability = analysis["probability"]
        height, width = analysis["baseline"].shape[:2]
        probability_full = np.asarray(
            Image.fromarray(probability.astype(np.float32)).resize((width, height), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
        change_mask = (probability_full >= settings.CHANGE_MAP_THRESHOLD).astype(np.uint8)
        before_indices = compute_spectral_indices(analysis["baseline"], analysis["baseline_map"])
        after_indices = compute_spectral_indices(analysis["normalized"], analysis["current_map"])
        regions = classify_change_regions(change_mask, before_indices, after_indices, min_region_size=8)
        type_areas: dict[str, int] = {}
        dynamic_areas: dict[str, int] = {}
        for region in regions:
            type_areas[region.change_type] = type_areas.get(region.change_type, 0) + region.area_pixels
            dynamic_areas[region.dynamics] = dynamic_areas.get(region.dynamics, 0) + region.area_pixels
        dominant_type = max(type_areas, key=type_areas.get) if type_areas else "unclassified"
        dominant_dynamics = max(dynamic_areas, key=dynamic_areas.get) if dynamic_areas else "appearance"

        temporal_scores = [float(item["signal"]) for item in entries[baseline_end + 1:] if item["valid"]]
        suppression = evaluate(
            raw_change_score=float(onset_entry["signal"]),
            before_q=reference_entry["quality"],
            after_q=onset_entry["quality"],
            registration_correlation=float(analysis["registration"]["correlation_after"]),
            radiometric_diff=float(onset_entry["radiometric_normalization"]["mean_delta_after"]),
            temporal_series=temporal_scores,
        )

        pixel_res = float(after_tile.resolution_m or before_tile.resolution_m or 10.0)
        changed_pixels = int(change_mask.sum())
        change_area_m2 = float(changed_pixels * pixel_res * pixel_res)
        mask_dir = settings.TILES_DIR / "change_masks"
        mask_dir.mkdir(parents=True, exist_ok=True)
        mask_filename = f"dense_{before_tile.tile_id}_{after_tile.tile_id}.png"
        mask_path = mask_dir / mask_filename
        Image.fromarray((probability_full * 255).clip(0, 255).astype(np.uint8)).save(mask_path)

        registration = analysis["registration"]
        trajectories = {
            "ndvi": [{"timestamp": item["tile"].acquisition_date.isoformat(), "value": obs["mean_ndvi"], "delta": obs["d_ndvi"]} for item, obs in zip(entries, observations) if item["modality"] == "optical"],
            "ndwi": [{"timestamp": item["tile"].acquisition_date.isoformat(), "value": obs["mean_ndwi"], "delta": obs["d_ndwi"]} for item, obs in zip(entries, observations) if item["modality"] == "optical"],
            "ndbi": [{"timestamp": item["tile"].acquisition_date.isoformat(), "value": obs["mean_ndbi"], "delta": obs["d_ndbi"]} for item, obs in zip(entries, observations) if item["modality"] == "optical"],
        }
        onset_observation = observations[onset_index]
        radiometric = onset_entry["radiometric_normalization"]
        evidence_items = [
            {
                "label": "Temporal persistence",
                "status": "pass",
                "value": f"{persistence_k} consecutive valid passes",
                "details": f"Onset {change_point.earliest_supported.isoformat()} confirmed {change_point.confirmed_at.isoformat()}",
            },
            {
                "label": "Sub-pixel co-registration",
                "status": "pass" if registration["is_aligned"] else "fail",
                "value": f"corr={registration['correlation_after']:.3f}; inliers={registration['inliers']}",
                "details": f"dx={registration['dx']} px, dy={registration['dy']} px via {registration['method']}",
            },
            {
                "label": "Radiometric histogram matching",
                "status": "pass" if radiometric["improved"] else "fail",
                "value": f"{radiometric['mean_delta_before']:.5f} -> {radiometric['mean_delta_after']:.5f}",
                "details": "Absolute mean radiometric difference before and after local histogram matching.",
            },
        ]
        if onset_entry["modality"] == "optical":
            evidence_items.extend([
                {
                    "label": "Vegetation index delta (NDVI)",
                    "status": "info",
                    "value": f"{float(onset_observation['d_ndvi']):+.4f}",
                    "details": "Onset-pass delta against the optical rolling median baseline.",
                },
                {
                    "label": "Built-up index delta (NDBI)",
                    "status": "info",
                    "value": f"{float(onset_observation['d_ndbi']):+.4f}",
                    "details": "Onset-pass delta against the optical rolling median baseline.",
                },
            ])
        evidence = {
            "d_ndvi": onset_observation["d_ndvi"],
            "d_ndwi": onset_observation["d_ndwi"],
            "d_ndbi": onset_observation["d_ndbi"],
            "persistence_count": persistence_k,
            "spectral_trajectories": trajectories,
            "registration_by_pass": [{"timestamp": item["tile"].acquisition_date.isoformat(), **(item.get("registration") or {})} for item in entries],
            "radiometric_verification_by_pass": [{"timestamp": item["tile"].acquisition_date.isoformat(), **(item.get("radiometric_normalization") or {})} for item in entries],
            "persistence_verification": persistence,
            "total_observations": len(entries),
            "usable_observations": len(valid_indices),
            "valid_pixel_ratio": onset_entry["quality"].valid_pixel_fraction,
            "registration_correlation": registration["correlation_after"],
            "registration_aligned": registration["is_aligned"],
            "cloud_fraction": onset_entry["quality"].cloud_fraction,
            "radiometric_diff": radiometric["mean_delta_after"],
            "items": evidence_items,
        }

        key_material = "|".join([
            f"{lon:.6f}", f"{lat:.6f}", date_from, date_to,
            str(baseline_n), str(persistence_k), f"{threshold:.4f}",
            *(str(item["tile"].tile_id) for item in entries),
        ])
        analysis_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
        result = session.execute(
            select(ChangeResult).where(ChangeResult.analysis_key == analysis_key)
        ).scalar_one_or_none()
        if result is None:
            result = ChangeResult(
                before_tile_id=before_tile.tile_id,
                after_tile_id=after_tile.tile_id,
                change_score=suppression.change_score,
                quality_score=suppression.quality_score,
                confidence=suppression.confidence,
                method="dense-multitemporal-change-point",
                is_placeholder_model=bool(analysis["feature_is_placeholder"]),
                analysis_key=analysis_key,
            )
            session.add(result)
        result.change_score = suppression.change_score
        result.quality_score = suppression.quality_score
        result.confidence = suppression.confidence
        result.change_area_m2 = round(change_area_m2, 1)
        result.change_mask_path = str(mask_path)
        result.reasons = suppression.reasons
        result.earliest_supported_observation = change_point.earliest_supported
        result.confirmed_observation = change_point.confirmed_at
        result.temporal_uncertainty_days = change_point.temporal_uncertainty_days
        result.persistence_status = change_point.status
        result.persistence_log = change_point.log
        result.observations = observations
        result.evidence = evidence
        result.registration = registration
        result.dominant_change_type = dominant_type
        result.dominant_dynamics = dominant_dynamics
        session.flush()

        return {
            "status": "ok",
            "is_fallback": False,
            "result_source": "backend",
            "change_id": str(result.change_id),
            "dominant_change_type": dominant_type,
            "dominant_dynamics": dominant_dynamics,
            "change_score": suppression.change_score,
            "quality_score": suppression.quality_score,
            "confidence": suppression.confidence,
            "change_area_m2": round(change_area_m2, 1),
            "change_area_hectares": round(change_area_m2 / 10000.0, 3),
            "change_summary": (
                f"{change_area_m2 / 10000.0:.2f} hectares of {dominant_type.replace('_', ' ')} "
                f"confirmed across {persistence_k} consecutive valid observations."
            ),
            "change_mask_path": str(mask_path),
            "change_mask_url": f"/static/tiles/change_masks/{mask_filename}",
            "earliest_supported_observation": change_point.earliest_supported.isoformat(),
            "confirmed_observation": change_point.confirmed_at.isoformat(),
            "temporal_uncertainty_days": change_point.temporal_uncertainty_days,
            "confirmation_lag_days": change_point.confirmation_lag_days,
            "observations": observations,
            "persistence": persistence,
            "evidence": evidence,
            "confidence_breakdown": suppression.confidence_breakdown,
            "confounds": [item.__dict__ for item in suppression.confounds],
            "registration": registration,
            "change_regions": [
                {
                    "region_id": region.region_id,
                    "change_type": region.change_type,
                    "dynamics": region.dynamics,
                    "confidence": region.confidence,
                    "area_pixels": region.area_pixels,
                    "area_m2": round(region.area_pixels * pixel_res * pixel_res, 1),
                    "centroid": region.centroid,
                    "bbox": region.bbox,
                    "mean_d_ndvi": region.mean_d_ndvi,
                    "mean_d_ndwi": region.mean_d_ndwi,
                    "mean_d_ndbi": region.mean_d_ndbi,
                    "elongation": region.elongation,
                    "rationale": region.rationale,
                }
                for region in regions
            ],
            "suppression_reasons": suppression.reasons,
            "before": {
                "tile_id": str(before_tile.tile_id),
                "acquisition_date": before_tile.acquisition_date.isoformat(),
                "thumbnail_path": before_tile.thumbnail_path,
                "thumbnail_url": f"/static/tiles/{before_tile.scene_id}/{Path(before_tile.thumbnail_path).name}",
                "sensor": before_tile.sensor,
            },
            "after": {
                "tile_id": str(after_tile.tile_id),
                "acquisition_date": after_tile.acquisition_date.isoformat(),
                "thumbnail_path": after_tile.thumbnail_path,
                "thumbnail_url": f"/static/tiles/{after_tile.scene_id}/{Path(after_tile.thumbnail_path).name}",
                "sensor": after_tile.sensor,
            },
            "confirmation": {
                "tile_id": str(confirmation_entry["tile"].tile_id),
                "acquisition_date": confirmation_entry["tile"].acquisition_date.isoformat(),
                "sensor": confirmation_entry["tile"].sensor,
                "modality": confirmation_entry["modality"],
            },
            "method": "dense-multitemporal-change-point",
            "is_placeholder_model": bool(analysis["feature_is_placeholder"]),
        }
