# Staging Prithvi-EO

TerreX's `backend/services/prithvi.py` prefers the supplied
`prithvi_int8.onnx` INT8 export, and otherwise looks for the official
`Prithvi_EO_V1_100M.pt` checkpoint, `config.json`, and `prithvi_mae.py` in
this directory. The legacy filename `prithvi_eo_v1.pt` is still accepted for
older local setups.

If the staged artifacts or ML dependencies are missing, TerreX transparently
falls back to a non-AI statistical patch-feature extractor (per-patch band
mean/std + edge energy) so change detection remains exercisable. Every
`ChangeResult` produced this way is tagged
`is_placeholder_model=True` / `method="feature-diff-placeholder"`, and the
UI shows a warning badge whenever a placeholder result is displayed.

## What to place here

- `Prithvi_EO_V1_100M.pt` - model weights
- `prithvi_int8.onnx` - preferred CPU ONNX Runtime model export
- `config.json` - model config (patch size, layers, embed dim, bands, mean/std)
- `prithvi_mae.py` - official Prithvi implementation used by the checkpoint

## Where to get it

- **Model**: Prithvi-EO 1.0 100M
- **Authors**: NASA IMPACT & IBM Research
- **Source**: Hugging Face `ibm-nasa-geospatial/Prithvi-EO-1.0-100M`
- **License**: Apache 2.0 (confirm on the current model card before use)
- **Paper**: "Foundation Models for Generalist Geospatial Artificial Intelligence"

## Staging steps

1. On a machine with internet access, run:
   `python scripts/stage_models.py`
2. For Docker, rebuild with the default Compose config. It passes
   `INSTALL_ML=true` and installs `backend/requirements-ml.txt`.
3. For local Python, install `backend/requirements-ml.txt` in the backend
   environment.
4. Restart the backend. `GET /api/system/status` should show
   `models.prithvi.staged: true` and `active_model: "prithvi-int8-onnx"`.

The real Prithvi path only runs when both before and after observations have
all six required bands in TerreX order: blue, green, red, NIR, SWIR1, SWIR2.
If either side is RGB-only or ambiguous, that comparison intentionally falls
back to the labelled placeholder feature extractor.

## Note on the change-detection head

Even with real Prithvi features, TerreX's change "head" starts as a simple,
documented feature-difference function (`_difference_to_change_map` in
`backend/services/change_detection.py`) per the project's instruction to
start simple. Swap in a trained head later without touching the rest of the
pipeline by replacing that one function.
