import re
from pathlib import Path


def test_no_legacy_feature_concept_outside_compatibility():
    root = Path(__file__).resolve().parents[1] / "src"
    for path in root.rglob("*.py"):
        if path.name != "compatibility.py":
            assert not re.search(
                r"skill|intelligence.contract", path.read_text(encoding="utf-8"), re.I
            ), path
