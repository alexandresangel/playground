"""Configuration loading with a migration-compatible environment fallback."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_CONFIG_ENV = "CAPTURE_CONFIG"
_LEGACY_CONFIG_ENV = "CHAT_CONFIG"


def load_config(base_dir: Path | None = None) -> dict[str, Any]:
    """Load CAPTURE_CONFIG, then legacy CHAT_CONFIG, then config.json."""
    raw = (os.getenv(_CONFIG_ENV) or "").strip()
    source = _CONFIG_ENV
    if not raw:
        raw = (os.getenv(_LEGACY_CONFIG_ENV) or "").strip()
        source = _LEGACY_CONFIG_ENV
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {source}: {exc}") from exc
    else:
        root = base_dir or Path.cwd()
        path = root / "config.json"
        if not path.is_file():
            raise RuntimeError(
                f"Set {_CONFIG_ENV} (or migration fallback {_LEGACY_CONFIG_ENV}) or create {path}."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Configuration root must be a JSON object")
    return data


def capture_config(config: dict[str, Any]) -> dict[str, Any]:
    block = config.get("capture")
    if isinstance(block, dict):
        return block
    legacy = config.get("intelligence_contract")
    return legacy if isinstance(legacy, dict) else {}


def storage_config(config: dict[str, Any]) -> dict[str, Any]:
    block = config.get("storage")
    return block if isinstance(block, dict) else {}


def azure_openai_config(config: dict[str, Any]) -> dict[str, Any]:
    block = config.get("azure_openai")
    return block if isinstance(block, dict) else {}


def integer_setting(block: dict[str, Any], key: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(block.get(key, default)))
    except (TypeError, ValueError):
        return default


def float_setting(block: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(block.get(key, default))
    except (TypeError, ValueError):
        return default
