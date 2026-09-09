"""Read-only source/asset provenance checks against the original workspace, not a runtime import."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REWORKS = ROOT / "reworks"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return {
        node.name: ast.dump(node, include_attributes=False)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


pairs = {
    "capture/src/capture/workflow/extraction.py": "skills/intelligence_contract/extract_xml.py",
    "diapason-agent/src/pascal/security/jwt.py": "dia_jwt/auth.py",
    "diapason-agent/src/pascal/security/deps.py": "dia_jwt/fastapi.py",
    "diapason-agent/src/pascal/security/setup.py": "auth_setup.py",
    "diapason-agent/src/pascal/sessions/blob_store.py": "session_store.py",
    "diapason-agent/src/pascal/tools/context.py": "mcp_context.py",
    "diapason-agent/src/pascal/tools/audience.py": "tool_audience.py",
    "diapason-agent/src/pascal/tools/sources.py": "source_extract.py",
    "diapason-agent/src/pascal/i18n/__init__.py": "i18n.py",
    "diapason-agent/src/pascal/build_info.py": "build_info.py",
    "capture/src/capture/adapters/blob.py": "blob_client.py",
}
results = []
for current, reference in pairs.items():
    candidate, original = REWORKS / current, ROOT / reference
    newer, older = functions(candidate), functions(original)
    results.append(
        {
            "path": current,
            "reference": reference,
            "byte_identical": digest(candidate) == digest(original),
            "identical_top_level_definitions": [
                name for name in newer if newer[name] == older.get(name)
            ],
            "changed_or_new_definitions": [
                name for name in newer if newer[name] != older.get(name)
            ],
            "removed_definitions": sorted(older.keys() - newer.keys()),
        }
    )
assets = []
original_config = ROOT / "skills/intelligence_contract/config"
for original in sorted(original_config.rglob("*")):
    if original.is_file():
        relative = original.relative_to(original_config)
        candidate = REWORKS / "capture/config" / relative
        assets.append(
            {
                "path": str(relative),
                "exists": candidate.exists(),
                "byte_identical": candidate.exists() and digest(original) == digest(candidate),
                "text_identical_utf8_lf": candidate.exists()
                and original.read_text(encoding="utf-8-sig")
                == candidate.read_text(encoding="utf-8-sig"),
                "sha256": digest(original),
            }
        )
print(json.dumps({"python": results, "capture_assets": assets}, indent=2))
