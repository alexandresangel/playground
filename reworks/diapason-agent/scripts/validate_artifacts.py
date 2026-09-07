"""Local static artifact checks; never confused with a real Terraform plan/deployment."""

import json
from pathlib import Path

import hcl2
import yaml

root = Path(__file__).resolve().parents[1]
with (root / "deploy/infra.tf").open(encoding="utf-8") as stream:
    infra = hcl2.load(stream)
assert infra.get("module")
for name in ("quality.yml", "deploy.yml"):
    document = yaml.safe_load((root / ".github/workflows" / name).read_text(encoding="utf-8"))
    assert document["jobs"]
deploy = yaml.safe_load((root / ".github/workflows/deploy.yml").read_text(encoding="utf-8"))
assert deploy["jobs"]["deploy"]["needs"] == "quality"
for relative in (
    "config.example.json",
    "evaluation/cases.example.json",
    "frontend/package-lock.json",
):
    json.loads((root / relative).read_text(encoding="utf-8"))
print("Terraform HCL, workflow YAML and configuration JSON parsed; deploy depends on quality.")
