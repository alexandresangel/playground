"""Optional audit against the original migration source."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT.parent / "diapason-agent-main"


def test_company_and_extraction_assets_unchanged():
    if not ORIGINAL.is_dir():
        pytest.skip("Original source is available only in the migration workspace")
    common = ROOT / "src/capture/common"
    for file in common.rglob("*.py"):
        old = ORIGINAL / file.relative_to(common)
        assert file.read_text(encoding="utf-8").rstrip() == old.read_text(encoding="utf-8").rstrip(), file
    for file in (ROOT / "config").rglob("*"):
        if file.is_file() and file.name != "upload.sh":
            old = ORIGINAL / "skills/intelligence_contract/config" / file.relative_to(ROOT / "config")
            assert file.read_text(encoding="utf-8").rstrip() == old.read_text(encoding="utf-8").rstrip(), file
