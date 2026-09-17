"""
Pure-array remote sensing algorithm modules for TerreX.

Every module in this package takes NumPy arrays and returns NumPy arrays /
dataclasses, with zero dependencies on databases, rasterio, or Qdrant. This
ensures the science is 100% unit-testable and isolated from I/O and storage.

`pipeline.analyze_change_pair` is the entry point: it chains registration,
radiometric normalization, cloud/quality masking, deep EO feature difference,
spectral difference, spatial/context consistency, evidence fusion and
false-alarm suppression into a single auditable `ChangeAnalysis`.
"""
from services.algorithms.registration import (
    register_image_pair,
    RegistrationResult,
    apply_transform,
    warp_footprint,
)
from services.algorithms.normalization import (
    normalize_histogram_match,
    normalize_relative_radiometry,
    NormalizationResult,
)
from services.algorithms.spectral import compute_spectral_indices, compute_spectral_deltas, SpectralIndices
from services.algorithms.change_classifier import classify_change_regions, ChangeRegion
from services.algorithms.masking import compute_quality_mask, joint_valid_mask, QualityMask
from services.algorithms.evidence import (
    EvidenceLayer,
    deep_evidence,
    deep_feature_difference,
    robust_probability,
    spatial_evidence,
    spectral_evidence,
)
from services.algorithms.fusion import fuse_evidence, FusionResult
from services.algorithms.suppression import suppress_false_alarms, SuppressionMaps
from services.algorithms.pipeline import (
    analyze_change_pair,
    ChangeAnalysis,
    Observation,
    PipelineStage,
    PIPELINE_VERSION,
)

__all__ = [
    "register_image_pair",
    "RegistrationResult",
    "apply_transform",
    "warp_footprint",
    "normalize_histogram_match",
    "normalize_relative_radiometry",
    "NormalizationResult",
    "compute_spectral_indices",
    "compute_spectral_deltas",
    "SpectralIndices",
    "classify_change_regions",
    "ChangeRegion",
    "compute_quality_mask",
    "joint_valid_mask",
    "QualityMask",
    "EvidenceLayer",
    "deep_evidence",
    "deep_feature_difference",
    "robust_probability",
    "spatial_evidence",
    "spectral_evidence",
    "fuse_evidence",
    "FusionResult",
    "suppress_false_alarms",
    "SuppressionMaps",
    "analyze_change_pair",
    "ChangeAnalysis",
    "Observation",
    "PipelineStage",
    "PIPELINE_VERSION",
]
