# Staging Prithvi-EO

TerreX's `backend/services/prithvi.py` looks for `prithvi_eo_v1.pt` and
`config.json` in this directory. If either is missing, it **transparently
falls back** to a non-AI statistical patch-feature extractor (per-patch band
mean/std + edge energy) so change detection (Feature 4) is exercisable —
every `ChangeResult` produced this way is tagged
`is_placeholder_model=True` / `method="feature-diff-placeholder"`, and the
UI shows a warning badge whenever a placeholder result is displayed.

## What to place here

- `prithvi_eo_v1.pt` — model weights
- `config.json` — model config (patch size, num layers, embed dim, etc.)

## Where to get it

- **Model**: Prithvi-EO (Prithvi-100M / Prithvi-EO-1.0 / Prithvi-EO-2.0)
- **Authors**: NASA IMPACT & IBM Research
- **Source**: Hugging Face `ibm-nasa-geospatial/Prithvi-EO-1.0-100M` (or the
  2.0 release, `ibm-nasa-geospatial/Prithvi-EO-2.0-300M`)
- **License**: Apache 2.0 (confirm on the current model card before use)
- **Paper**: "Foundation Models for Generalist Geospatial Artificial Intelligence"

## Staging steps

1. On a machine with internet access, download the checkpoint and config
   from the Hugging Face repo above.
2. Copy both files into this directory (`models/prithvi/`).
3. Install `terratorch` (or the loader library matching the release you
   staged) — uncomment it in `backend/requirements.txt` and rebuild.
4. Implement/verify the loader in `_RealPrithvi.__init__` /
   `_RealPrithvi.extract` in `backend/services/prithvi.py` matches the
   exact checkpoint format you staged (Prithvi releases have changed
   loader APIs between 1.0 and 2.0 — check the model card's example code).
5. Restart the backend. `GET /api/system/status` should show
   `models.prithvi.staged: true`.

## Note on the change-detection head

Even with real Prithvi features, TerreX's change "head" starts as a simple,
documented feature-difference function (`_difference_to_change_map` in
`backend/services/change_detection.py`) — per the project's explicit
instruction to start simple. Swap in a trained head later without touching
the rest of the pipeline by replacing that one function.
