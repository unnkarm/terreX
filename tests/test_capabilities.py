import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.capabilities import CAPABILITIES


def test_all_six_mandatory_capabilities_are_reported_implemented():
    assert [item["id"] for item in CAPABILITIES] == [
        "2.2.1", "2.2.2", "2.2.3", "2.2.4", "2.2.5", "2.2.6",
    ]
    assert all(item["status"] == "implemented" for item in CAPABILITIES)
    assert all(item["evidence"] for item in CAPABILITIES)
