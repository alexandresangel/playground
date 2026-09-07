"""Trade-type catalog and prompt loading, preserving the legacy blob layout."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

from capture.blob_store import read_blob_text
from capture.config import capture_config, integer_setting, storage_config
from capture.constants import DEFAULT_CATALOG_BLOB, LEGACY_CATALOG_PREFIX


class PromptCatalog:
    def __init__(self, config: dict[str, Any], project_root: Path) -> None:
        self._config = config
        self._capture = capture_config(config)
        self._storage = storage_config(config)
        self._project_root = project_root
        self._lock = threading.Lock()
        self._catalog: dict[str, Any] = {}
        self._version = ""
        self._source = ""
        self._prompt_cache: dict[str, tuple[float, str]] = {}

    @property
    def ready(self) -> bool:
        with self._lock:
            return bool(self._catalog)

    @property
    def version(self) -> str:
        with self._lock:
            return self._version

    @property
    def source(self) -> str:
        with self._lock:
            return self._source

    def _backend(self) -> str:
        explicit = str(self._capture.get("catalog_backend") or "").strip().lower()
        if explicit:
            if explicit not in {"blob", "filesystem"}:
                raise RuntimeError("capture.catalog_backend must be 'blob' or 'filesystem'")
            return explicit
        return "blob" if str(self._storage.get("account_name") or "").strip() else "filesystem"

    def _catalog_blob(self) -> str:
        return str(self._capture.get("catalog_blob") or DEFAULT_CATALOG_BLOB).strip()

    def _local_config_root(self) -> Path:
        configured = str(self._capture.get("catalog_directory") or "").strip()
        return Path(configured) if configured else self._project_root / "config"

    def _read_catalog(self) -> tuple[dict[str, Any], str, str]:
        if self._backend() == "blob":
            account = str(self._storage.get("account_name") or "").strip()
            container = str(self._storage.get("config_container") or "agent-config").strip()
            if not account:
                raise RuntimeError("storage.account_name is required for the blob catalog")
            blob_name = self._catalog_blob()
            raw = read_blob_text(account, container, blob_name)
            source = f"blob:{container}/{blob_name}"
        else:
            path = self._local_config_root() / "catalog.json"
            raw = path.read_text(encoding="utf-8")
            source = f"file:{path}"
        try:
            catalog = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Capture catalog is invalid JSON ({source}): {exc}") from exc
        if not isinstance(catalog, dict):
            raise RuntimeError(f"Capture catalog must be a JSON object ({source})")
        version = str(catalog.get("version") or catalog.get("catalog_version") or "").strip()
        if not version:
            version = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return catalog, version, source

    def initialize(self) -> dict[str, Any]:
        catalog, version, source = self._read_catalog()
        with self._lock:
            self._catalog = catalog
            self._version = version
            self._source = source
            self._prompt_cache.clear()
        return {"ok": True, "version": version, "source": source}

    @staticmethod
    def _parse_entry(
        entry: Any, *, default_view_entity: str, default_menu_name: str
    ) -> tuple[list[str], str, str]:
        if isinstance(entry, list):
            types = [str(item or "").strip() for item in entry if str(item or "").strip()]
            return types, default_view_entity, default_menu_name or default_view_entity
        if isinstance(entry, dict):
            raw_types = entry.get("types") or []
            types = [str(item or "").strip() for item in raw_types if str(item or "").strip()]
            view = str(entry.get("view_entity") or default_view_entity).strip()
            menu = str(entry.get("menu_name") or default_menu_name or view).strip()
            return types, view, menu
        return [], default_view_entity, default_menu_name or default_view_entity

    def _type_map(self) -> dict[str, dict[str, str]]:
        with self._lock:
            catalog = dict(self._catalog)
        prompts = catalog.get("prompts")
        if not isinstance(prompts, dict):
            return {}
        default_view = str(catalog.get("default_view_entity") or "").strip()
        default_menu = str(catalog.get("default_menu_name") or "").strip()
        result: dict[str, dict[str, str]] = {}
        for prompt_path, entry in prompts.items():
            path = str(prompt_path or "").strip()
            if not path:
                continue
            types, view, menu = self._parse_entry(
                entry,
                default_view_entity=default_view,
                default_menu_name=default_menu,
            )
            for trade_type in types:
                result[trade_type] = {
                    "trade_type": trade_type,
                    "prompt_blob": path,
                    "view_entity": view,
                    "menu_name": menu or view,
                }
        return result

    def trade_types(self) -> list[str]:
        return sorted(self._type_map())

    def trade_type_config(self, trade_type: str) -> dict[str, str]:
        key = (trade_type or "").strip()
        if not key:
            raise ValueError("trade_type is required")
        by_type = self._type_map()
        if key in by_type:
            return by_type[key]
        with self._lock:
            catalog = dict(self._catalog)
        default_prompt = str(catalog.get("default_prompt") or "").strip()
        if not default_prompt:
            known = ", ".join(sorted(by_type))
            raise ValueError(f"Unknown trade_type {key!r} (known: {known})")
        default_view = str(catalog.get("default_view_entity") or "").strip()
        default_menu = str(catalog.get("default_menu_name") or default_view).strip()
        return {
            "trade_type": key,
            "prompt_blob": default_prompt,
            "view_entity": default_view,
            "menu_name": default_menu,
        }

    def _prompt_path(self, prompt_blob: str) -> str:
        path = prompt_blob.strip().lstrip("/")
        if path.startswith(f"{LEGACY_CATALOG_PREFIX}/"):
            return path
        return f"{LEGACY_CATALOG_PREFIX}/{path}"

    def prompt_text(self, prompt_blob: str) -> str:
        key = (prompt_blob or "").strip()
        if not key:
            raise ValueError("prompt_blob is required")
        now = time.monotonic()
        with self._lock:
            cached = self._prompt_cache.get(key)
            if cached and cached[0] > now:
                return cached[1]

        if self._backend() == "blob":
            account = str(self._storage.get("account_name") or "").strip()
            container = str(self._storage.get("config_container") or "agent-config").strip()
            text = read_blob_text(account, container, self._prompt_path(key))
        else:
            text = (self._local_config_root() / key).read_text(encoding="utf-8")
        ttl = integer_setting(self._capture, "cache_ttl_seconds", 300)
        with self._lock:
            self._prompt_cache[key] = (now + ttl, text)
        return text

    def metadata(self) -> dict[str, Any]:
        return {
            "enabled": self._capture.get("enabled") is not False,
            "trade_types": self.trade_types(),
            "prompt_version": self.version,
        }
