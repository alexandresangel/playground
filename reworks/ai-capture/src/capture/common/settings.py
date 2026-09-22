"""Load config.json locally, or CHAT_CONFIG env (ACA secret) at runtime."""

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
    raw = os.getenv("CHAT_CONFIG", "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in CHAT_CONFIG: {exc}") from exc
    else:
        local = base / "config.local.json"
        default = base / "config.json"
        path = local if local.is_file() else default
        if not path.is_file():
            raise RuntimeError(
                f"Missing {local.name} or {default.name}. "
                f"Copy config.example.json → config.local.json (preferred) or config.json, "
                "or set CHAT_CONFIG (Container App secret)."
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
            "Missing registry_url in config (required in CHAT_CONFIG / config JSON)."
        )
    _config = data
    return _config


def assistant_name(config: dict | None = None) -> str:
    cfg = config if config is not None else load_config()
    ui = cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}
    name = str(ui.get("assistant_name", "Pascal") or "").strip()
    return name or "Pascal"


def assistant_identity(config: dict | None = None) -> str:
    """Persona for the LLM (separate from BI system_prompt)."""
    cfg = config if config is not None else load_config()
    ui = cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}
    return str(ui.get("assistant_identity", "") or "").strip()


def assistant_identity_llm_block(config: dict | None = None) -> str:
    text = assistant_identity(config)
    if not text:
        return ""
    return f"\n\n---\n**Assistant identity:**\n{text}\n"
