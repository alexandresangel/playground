"""Capture prompts using the existing company config blob paths."""

from __future__ import annotations
from typing import Any, Dict, Tuple
import hashlib
import json
import threading
import time

from blob_client import read_blob_text

LEGACY_BLOB_PREFIX = "skills/intelligence-contract"
DEFAULT_CATALOG_BLOB = f"{LEGACY_BLOB_PREFIX}/catalog.json"

_lock = threading.Lock()
_catalog: Dict[str, Any] = {}
_catalog_version = ""
_catalog_source = ""
_prompt_cache: Dict[str, Tuple[float, str]] = {}

def capture_config(config: Dict[str, Any]) -> Dict[str, Any]:
    block = config.get("intelligence_contract")
    return block if isinstance(block, dict) else {}


def capture_enabled(config: Dict[str, Any]) -> bool:
    return capture_config(config).get("enabled") is True


def capture_view_entity(config: Dict[str, Any]) -> str:
    return str(capture_config(config).get("view_entity", "loanDeposit") or "loanDeposit").strip()


def capture_temperature(config: Dict[str, Any]) -> float:
    raw = capture_config(config).get("temperature", 0.5)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.5


def _storage(config: Dict[str, Any]) -> Dict[str, Any]:
    block = config.get("storage")
    return block if isinstance(block, dict) else {}


def _storage_account(config: Dict[str, Any]) -> str:
    return str(_storage(config).get("account_name", "") or "").strip()


def _config_container(config: Dict[str, Any]) -> str:
    name = str(_storage(config).get("config_container", "") or "").strip()
    return name or "agent-config"


def _catalog_blob(config: Dict[str, Any]) -> str:
    name = str(
        capture_config(config).get("catalog_blob", "") or ""
    ).strip()
    return name or DEFAULT_CATALOG_BLOB


def _prompt_blob_path(prompt_blob: str) -> str:
    """Resolve catalog-relative prompt path under the legacy blob prefix."""
    name = (prompt_blob or "").strip().lstrip("/")
    if name.startswith(f"{LEGACY_BLOB_PREFIX}/"):
        return name
    return f"{LEGACY_BLOB_PREFIX}/{name}"


def _cache_ttl(config: Dict[str, Any]) -> int:
    raw = capture_config(config).get("cache_ttl_seconds", 300)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 300


def _blob_source(config: Dict[str, Any], blob_name: str) -> str:
    return f"blob:{_config_container(config)}/{blob_name}"


def _compute_catalog_version(catalog: Dict[str, Any], raw_text: str) -> str:
    explicit = str(catalog.get("version", "") or catalog.get("catalog_version", "") or "").strip()
    if explicit:
        return explicit
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:12]


def _load_catalog(config: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str]:
    account = _storage_account(config)
    container = _config_container(config)
    blob_name = _catalog_blob(config)
    if not account:
        raise RuntimeError("storage.account_name is required")
    raw = read_blob_text(account, container, blob_name)
    catalog = json.loads(raw)
    if not isinstance(catalog, dict):
        raise RuntimeError(f"{blob_name} must be a JSON object")
    version = _compute_catalog_version(catalog, raw)
    source = _blob_source(config, blob_name)
    return catalog, version, source


def init_capture_prompts(config: Dict[str, Any]) -> Dict[str, Any]:
    global _catalog, _catalog_version, _catalog_source, _prompt_cache
    catalog, version, source = _load_catalog(config)
    with _lock:
        _catalog = catalog
        _catalog_version = version
        _catalog_source = source
        _prompt_cache.clear()
    return {"ok": True, "version": version, "source": source}


def refresh_capture_prompts(config: Dict[str, Any]) -> Dict[str, Any]:
    return init_capture_prompts(config)


def capture_prompt_version() -> str:
    with _lock:
        return _catalog_version


def capture_prompt_source() -> str:
    with _lock:
        return _catalog_source


def _default_view_entity(catalog: Dict[str, Any]) -> str:
    return str(catalog.get("default_view_entity", "") or "").strip()


def _default_menu_name(catalog: Dict[str, Any]) -> str:
    return str(catalog.get("default_menu_name", "") or "").strip()


def _parse_prompt_entry(
    entry: Any, *, default_view_entity: str, default_menu_name: str
) -> tuple[list[str], str, str]:
    if isinstance(entry, list):
        types = [str(tt or "").strip() for tt in entry if str(tt or "").strip()]
        menu_name = default_menu_name or default_view_entity
        return types, default_view_entity, menu_name
    if isinstance(entry, dict):
        raw_types = entry.get("types") or []
        types = [str(tt or "").strip() for tt in raw_types if str(tt or "").strip()]
        view_entity = str(entry.get("view_entity", "") or default_view_entity).strip()
        menu_name = str(
            entry.get("menu_name", "") or default_menu_name or view_entity
        ).strip()
        return types, view_entity, menu_name
    return [], default_view_entity, default_menu_name or default_view_entity


def _trade_type_map(catalog: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    prompts = catalog.get("prompts")
    if not isinstance(prompts, dict):
        return out
    default_ve = _default_view_entity(catalog)
    default_menu = _default_menu_name(catalog)
    for prompt_path, entry in prompts.items():
        path = str(prompt_path or "").strip()
        if not path:
            continue
        types, _ve, _menu = _parse_prompt_entry(
            entry, default_view_entity=default_ve, default_menu_name=default_menu
        )
        for tt in types:
            out[tt] = path
    return out


def _view_entity_map(catalog: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    prompts = catalog.get("prompts")
    if not isinstance(prompts, dict):
        return out
    default_ve = _default_view_entity(catalog)
    default_menu = _default_menu_name(catalog)
    for _prompt_path, entry in prompts.items():
        types, ve, _menu = _parse_prompt_entry(
            entry, default_view_entity=default_ve, default_menu_name=default_menu
        )
        if not ve:
            continue
        for tt in types:
            out[tt] = ve
    return out


def _menu_name_map(catalog: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    prompts = catalog.get("prompts")
    if not isinstance(prompts, dict):
        return out
    default_ve = _default_view_entity(catalog)
    default_menu = _default_menu_name(catalog)
    for _prompt_path, entry in prompts.items():
        types, ve, menu_name = _parse_prompt_entry(
            entry, default_view_entity=default_ve, default_menu_name=default_menu
        )
        if not menu_name:
            menu_name = ve
        if not menu_name:
            continue
        for tt in types:
            out[tt] = menu_name
    return out


def _default_prompt(catalog: Dict[str, Any]) -> str:
    return str(catalog.get("default_prompt", "") or "").strip()


def capture_trade_types() -> list[str]:
    with _lock:
        catalog = dict(_catalog)
    return sorted(_trade_type_map(catalog).keys())


def get_trade_type_config(trade_type: str) -> Dict[str, str]:
    key = (trade_type or "").strip()
    if not key:
        raise ValueError("trade_type is required")
    with _lock:
        catalog = dict(_catalog)
    by_type = _trade_type_map(catalog)
    prompt_blob = by_type.get(key) or _default_prompt(catalog)
    if not prompt_blob:
        known = ", ".join(sorted(by_type.keys()))
        raise ValueError(
            f"Unknown trade_type {key!r} (no default_prompt; known: {known})"
        )
    ve_map = _view_entity_map(catalog)
    menu_map = _menu_name_map(catalog)
    default_ve = _default_view_entity(catalog)
    default_menu = _default_menu_name(catalog)
    view_entity = ve_map.get(key) or default_ve
    menu_name = menu_map.get(key) or default_menu or view_entity
    result: Dict[str, str] = {"trade_type": key, "prompt_blob": prompt_blob}
    if view_entity:
        result["view_entity"] = view_entity
    if menu_name:
        result["menu_name"] = menu_name
    return result


def get_prompt_text(config: Dict[str, Any], prompt_blob: str) -> str:
    blob_name = (prompt_blob or "").strip()
    if not blob_name:
        raise ValueError("prompt_blob is required")
    ttl = _cache_ttl(config)
    now = time.time()
    with _lock:
        cached = _prompt_cache.get(blob_name)
        if cached and cached[0] > now:
            return cached[1]

    account = _storage_account(config)
    container = _config_container(config)
    text = read_blob_text(account, container, _prompt_blob_path(blob_name))
    with _lock:
        _prompt_cache[blob_name] = (now + ttl, text)
    return text
