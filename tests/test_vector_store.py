import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.vector_store import _sensor_aliases


def test_sensor_aliases_include_common_sentinel2_names():
    aliases = _sensor_aliases("Sentinel-2")

    assert "Sentinel-2" in aliases
    assert "Sentinel-2 MSI" in aliases
    assert "sentinel2" in aliases


def test_sensor_aliases_preserve_unknown_sensor():
    assert _sensor_aliases("Cartosat-3") == ["Cartosat-3"]
