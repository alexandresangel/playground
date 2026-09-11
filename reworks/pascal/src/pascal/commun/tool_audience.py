"""MCP tool audience: user-facing vs technical (chat @ menu)."""

from __future__ import annotations

from typing import Any, Dict


def is_technical_tool_name(tool_name: str) -> bool:
    name = (tool_name or "").strip()
    if not name:
        return False
    if name.endswith("Version"):
        return True
    if name.startswith("executePivotModel"):
        return True
    if name.endswith("Page"):
        return True
    return False


def audience_from_raw(raw: Dict[str, Any]) -> str:
    native = raw.get("name")
    if isinstance(native, str) and is_technical_tool_name(native):
        return "technical"
    meta = raw.get("_meta")
    if meta is None:
        meta = raw.get("meta")
    if isinstance(meta, dict):
        aud = meta.get("audience")
        if isinstance(aud, str) and aud.strip():
            return aud.strip().lower()
    return "user"


def is_chat_api_listed(audience: str) -> bool:
    return audience != "technical"


def is_tool_mentionable(
    native_name: str,
    qualified_name: str,
    audience: str,
    exclude_rules: list[str],
) -> bool:
    if not is_chat_api_listed(audience):
        return False
    if not exclude_rules:
        return True
    candidates = {native_name.lower(), qualified_name.lower()}
    for rule in exclude_rules:
        r = rule.lower()
        if r.startswith("*") and len(r) > 1:
            suffix = r[1:]
            if any(c.endswith(suffix) for c in candidates):
                return False
        elif r in candidates:
            return False
    return True