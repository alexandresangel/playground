from __future__ import annotations
from pathlib import Path
import yaml

from cash_flow_forecast.contracts.rules import Ruleset


def load_ruleset_from_yaml(path: str | Path) -> Ruleset:
    """Load a typed ruleset from a YAML file."""

    ruleset_path = Path(path)
    with ruleset_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    return Ruleset.model_validate(payload)
