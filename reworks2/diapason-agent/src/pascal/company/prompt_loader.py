"""System prompt from config blob (storage.config_container), else local system_prompt.md."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Tuple

from blob_client import read_blob_text

SYSTEM_PROMPT_FILE = "system_prompt.md"
DEFAULT_SYSTEM_PROMPT_BLOB = "system_prompt.md"

_lock = threading.Lock()
_prompt = ""
_source = ""


def _storage(config: Dict[str, Any]) -> Dict[str, Any]:
    block = config.get("storage")
    return block if isinstance(block, dict) else {}


def _account(config: Dict[str, Any]) -> str:
    return str(_storage(config).get("account_name", "") or "").strip()


def _config_container(config: Dict[str, Any]) -> str:
    name = str(_storage(config).get("config_container", "") or "").strip()
    return name or "agent-config"


def _system_prompt_blob(config: Dict[str, Any]) -> str:
    prompt = config.get("prompt") if isinstance(config.get("prompt"), dict) else {}
    name = str(prompt.get("system_prompt_blob", "") or "").strip()
    return name or DEFAULT_SYSTEM_PROMPT_BLOB


def _load_from_file(base_dir: Path) -> str:
    path = base_dir / SYSTEM_PROMPT_FILE
    if not path.is_file():
        raise RuntimeError(f"Missing {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Empty {path}")
    return text


def _load_from_blob(config: Dict[str, Any]) -> Tuple[str, str]:
    account = _account(config)
    if not account:
        raise RuntimeError("storage.account_name is required to load system prompt from blob")
    container = _config_container(config)
    blob = _system_prompt_blob(config)
    text = read_blob_text(account, container, blob).strip()
    if not text:
        raise RuntimeError(f"Empty system prompt from blob:{container}/{blob}")
    return text, f"blob:{container}/{blob}"


def _fetch(config: Dict[str, Any], base_dir: Path) -> Tuple[str, str]:
    # Prefer config blob when storage is configured; local file for offline/unit use.
    if _account(config):
        return _load_from_blob(config)
    return _load_from_file(base_dir), "file"


def init_system_prompt(config: Dict[str, Any], base_dir: Path) -> str:
    global _prompt, _source
    text, source = _fetch(config, base_dir)
    with _lock:
        _prompt = text
        _source = source
    return text


def get_system_prompt() -> str:
    with _lock:
        return _prompt


def prompt_source() -> str:
    with _lock:
        return _source


def refresh_system_prompt(config: Dict[str, Any], base_dir: Path) -> Dict[str, Any]:
    text, source = _fetch(config, base_dir)
    with _lock:
        global _prompt, _source
        _prompt = text
        _source = source
    return {
        "ok": True,
        "source": source,
        "length": len(text),
        "blob": _system_prompt_blob(config) if _account(config) else None,
    }
