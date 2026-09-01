"""
Pure-array remote sensing algorithm modules for TerreX.

Every module in this package takes NumPy arrays and returns NumPy arrays / dataclasses,
with zero dependencies on databases, rasterio, or Qdrant. This ensures the science is
100% unit-testable and isolated from I/O and storage.
"""
from services.algorithms.registration import register_image_pair, RegistrationResult
from services.algorithms.normalization import normalize_histogram_match
from services.algorithms.spectral import compute_spectral_indices, compute_spectral_deltas, SpectralIndices
from services.algorithms.change_classifier import classify_change_regions, ChangeRegion

__all__ = [
    "register_image_pair",
    "RegistrationResult",
    "normalize_histogram_match",
    "compute_spectral_indices",
    "compute_spectral_deltas",
    "SpectralIndices",
    "classify_change_regions",
    "ChangeRegion",
]
