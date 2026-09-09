import ast
import hashlib
import json
import re
from pathlib import Path


def test_original_prompt_and_catalog_bytes():
    config = Path(__file__).resolve().parents[1] / "config"
    manifest = json.loads((config / "source-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 8
    for name, expected in manifest.items():
        assert hashlib.sha256((config / name).read_bytes()).hexdigest() == expected, name


def test_no_legacy_feature_concept_outside_compatibility():
    root = Path(__file__).resolve().parents[1] / "src"
    for path in root.rglob("*.py"):
        if path.name != "compatibility.py":
            assert not re.search(
                r"skill|intelligence.contract", path.read_text(encoding="utf-8"), re.I
            ), path


def test_business_layers_do_not_depend_on_protocol_front_doors():
    source = Path(__file__).resolve().parents[1] / "src/capture"
    for package in ("workflow", "adapters"):
        for path in (source / package).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            assert not any(name.startswith(("mcp", "capture.api")) for name in imports), path
