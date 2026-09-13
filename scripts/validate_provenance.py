import json
from pathlib import Path
from typing import Optional, List
from datetime import datetime

class ProvenanceMetadata:
    """Dependency-free strict validator shared by CLI and ingestion pre-checks."""
    ALLOWED_DATASETS = {"Sentinel-2 L2A", "Sentinel-1 GRD", "Landsat 8/9 C2L2", "AWiFS", "LISS-III", "LISS-IV", "Cartosat-2S"}
    def __init__(self, **data):
        required = ("source_portal", "underlying_dataset", "satellite", "sensor", "acquisition_date", "resolution_m", "bounding_box", "license", "download_date", "ps_named_source")
        missing = [key for key in required if key not in data]
        if missing: raise ValueError(f"Missing fields: {', '.join(missing)}")
        if not str(data["satellite"]).strip() or not str(data["sensor"]).strip() or not str(data["license"]).strip(): raise ValueError("satellite, sensor, and license must be non-empty")
        if data["underlying_dataset"] not in self.ALLOWED_DATASETS: raise ValueError(f"Unsupported underlying_dataset: {data['underlying_dataset']}")
        for key in ("acquisition_date", "download_date"):
            try: datetime.strptime(str(data[key]), "%Y-%m-%d")
            except ValueError as exc: raise ValueError(f"{key} must be YYYY-MM-DD") from exc
        if float(data["resolution_m"]) <= 0: raise ValueError("resolution_m must be greater than zero")
        bbox = data["bounding_box"]
        if not isinstance(bbox, list) or len(bbox) != 4: raise ValueError("bounding_box must contain four numbers")
        min_lon, min_lat, max_lon, max_lat = map(float, bbox)
        if min_lon > max_lon or min_lat > max_lat or not (-180 <= min_lon <= max_lon <= 180) or not (-90 <= min_lat <= max_lat <= 90): raise ValueError("Invalid bounding_box")
        cloud = data.get("cloud_cover_pct")
        if cloud is not None and not (0 <= float(cloud) <= 100): raise ValueError("cloud_cover_pct must be between 0 and 100")
        self.__dict__.update(data)


def validate_sidecar(tif_path: Path) -> ProvenanceMetadata:
    """
    Validates that a strict .provenance.json sidecar exists for the given GeoTIFF.
    """
    # E.g., image.tif -> image.provenance.json
    sidecar_path = tif_path.with_name(f"{tif_path.stem}.provenance.json")
    
    if not sidecar_path.exists():
        raise FileNotFoundError(
            f"Missing provenance sidecar for {tif_path.name}. "
            f"Expected {sidecar_path.name} in the same directory."
        )

    with open(sidecar_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # This will raise pydantic ValidationError if the schema is violated
    return ProvenanceMetadata(**data)


def validate_incoming_directory(incoming_dir: Path) -> list[Path]:
    """Validate every GeoTIFF recursively and return offending paths."""
    errors: list[Path] = []
    for tif_path in sorted(list(incoming_dir.rglob("*.tif")) + list(incoming_dir.rglob("*.tiff"))):
        try:
            validate_sidecar(tif_path)
        except Exception as exc:
            errors.append(Path(f"{tif_path}: {exc}"))
    return errors

if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1] / "data" / "incoming"
    if target.is_dir():
        errors = validate_incoming_directory(target)
        if errors:
            print("Provenance validation failed:")
            print("\n".join(f"- {error}" for error in errors))
            sys.exit(1)
        print(f"Provenance validation successful for {target}")
    else:
        try:
            validate_sidecar(target)
            print("Validation successful!")
        except Exception as exc:
            print(f"Validation failed: {exc}")
            sys.exit(1)
