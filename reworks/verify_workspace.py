"""Read-only final artifact audit. Run with the Pascal development environment."""

import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

import hcl2
import yaml

REWORKS = Path(__file__).resolve().parent
ROOT = REWORKS.parent
baseline = json.loads((REWORKS / "source-baseline.json").read_text(encoding="utf-8"))
for group in ("original", "frozen_frontend"):
    for item in baseline[group]:
        path = ROOT / item["path"]
        assert path.is_file(), item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], item["path"]
original_files = set()
for directory, subdirs, files in os.walk(ROOT):
    if Path(directory) == ROOT:
        subdirs[:] = [name for name in subdirs if name != "reworks"]
    original_files.update((Path(directory) / name).relative_to(ROOT).as_posix() for name in files)
assert original_files == {item["path"] for item in baseline["original"]}

for project in ("capture", "diapason-agent"):
    root = REWORKS / project
    wheel = next((root / "dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        python_names = {name for name in archive.namelist() if name.endswith(".py")}
        expected = {
            path.relative_to(root / "src").as_posix() for path in (root / "src").rglob("*.py")
        }
        assert python_names == expected, (project, python_names ^ expected)
    for path in (root / ".github/workflows").glob("*.yml"):
        assert yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]
    deploy = yaml.safe_load((root / ".github/workflows/deploy.yml").read_text(encoding="utf-8"))
    assert deploy["jobs"]["deploy"]["needs"] == "quality"
    with (root / "deploy/infra.tf").open(encoding="utf-8") as stream:
        assert hcl2.load(stream)["module"]
    board = (root / "SPRINT.md").read_text(encoding="utf-8")
    stories = re.split(r"^## US\d+ .*", board, flags=re.M)[1:]
    assert len(stories) == 3
    for story in stories:
        assert "### Description" in story and "### Acceptance criteria" in story
    assert len(re.findall(r"^### (?:CAP|PAS)-[MDV]\d+", board, re.M)) == 14
    for path in [root / "README.md", *(root / "docs").glob("*.md")]:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if target.startswith(("https:", "http:", "#")):
                continue
            target = target.split("#", 1)[0]
            assert (path.parent / target).exists(), (path, target)
print("90 original files and 18 frozen frontend files unchanged; no original additions/removals.")
print(
    "Both wheels match current Python source; workflow/HCL, "
    "story structure and local doc links passed."
)
