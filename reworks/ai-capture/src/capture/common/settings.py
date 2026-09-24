"""Load config.local.json / config.json locally, or CAPTURE_CONFIG env (ACA secret) at runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path

_BASE = Path(__file__).resolve().parent
_config: dict | None = None


def load_config(base_dir: Path | None = None) -> dict:
    global _config
    if _config is not None:
        return _config

    base = base_dir or _BASE
    raw = os.getenv("CAPTURE_CONFIG", "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in CAPTURE_CONFIG: {exc}") from exc
    else:
        local = base / "config.local.json"
        default = base / "config.json"
        path = local if local.is_file() else default
        if not path.is_file():
            raise RuntimeError(
                f"Missing {local.name} or {default.name}. "
                f"Copy config.example.json → config.local.json (preferred) or config.json, "
                "or set CAPTURE_CONFIG (Container App secret)."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Config root must be a JSON object.")
    registry_url = data.get("registry_url")
    if not isinstance(registry_url, str) or not registry_url.strip():
        raise RuntimeError(
            "Missing registry_url in config (required in CAPTURE_CONFIG / config JSON)."
        )
    _config = data
    return _config
