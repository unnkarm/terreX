---
name: change-detection-engine
description: Deep reference for TerreX change detection algorithms. Use this skill when working on change detection logic, spectral indices, co-registration, false-alarm suppression, Prithvi-EO feature extraction, or the change classification pipeline.
---

# Change Detection Engine

## When to Use
- Working on `change_detection.py`, `dense_change_detection.py`, `false_alarm.py`
- Modifying spectral indices (NDVI/NDWI/NDBI), co-registration, or change classification
- Debugging why a change was suppressed or why a class was wrong

## Pipeline

```
Before + After GeoTIFF
  ? Co-registration (ORB/SIFT)          registration.py
  ? Spectral Indices (NDVI/NDWI/NDBI)   spectral.py
  ? Feature Extraction                   prithvi.py
      ONNX INT8 preferred ? Torch ? statistical fallback
  ? Change Map (threshold: CHANGE_MAP_THRESHOLD=0.20)
  ? False-Alarm Suppression              false_alarm.py
      cloud > 0.35 OR quality < 0.4 ? reject
  ? Semantic Classification (4 classes)  change_classifier.py
  ? Persistence (CHANGE_PERSISTENCE_K=2) time_series_change.py
  ? ChangeResult saved to DB
```

## Classification Classes

| Class | Signal |
|-------|--------|
| `construction` | NDVI? + NDBI? |
| `road_development` | Elongated morphology + infrastructure spectral |
| `water_extent` | NDWI shift + low SWIR |
| `clearance` | NDVI? without built-up or water |

## Key Thresholds (all in `config.py`)

`CLOUD_FRACTION_MAX=0.35` · `MIN_QUALITY_SCORE=0.4` · `CHANGE_MAP_THRESHOLD=0.20` · `CHANGE_PROB_THRESHOLD=0.5` · `CHANGE_PERSISTENCE_K=2`

## Placeholder Contract
If Prithvi not staged ? `is_placeholder_model=True` on every result. Statistical fallback (mean/std/edge energy) runs instead. UI shows warning banner — never suppress this flag.

## Model Staging
```bash
python scripts/stage_models.py
# Expects: models/prithvi/prithvi_int8.onnx (preferred) or models/prithvi/prithvi.pt
```
