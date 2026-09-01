# Trained change-detection head (optional, future work)

Currently unused. TerreX's MVP change detection (`backend/services/change_detection.py`)
computes a per-patch feature-difference map from Prithvi (or its placeholder)
features — a simple, explainable approach used deliberately as the starting
point, per the project brief ("Start with a simple feature-difference approach
if a trained change model is unavailable").

If you later train a dedicated change-detection head (e.g. a siamese
difference network on Prithvi features, or a full bi-temporal segmentation
model), stage its weights here and replace the single function
`_difference_to_change_map(before_features, after_features) -> HxW map` in
`backend/services/change_detection.py`. Nothing else in the pipeline needs
to change — false-alarm suppression, ranking, and the API/UI all consume
the same output shape regardless of which method produced it.
