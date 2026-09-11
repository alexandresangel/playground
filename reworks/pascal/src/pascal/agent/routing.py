"""Resolve the existing explicit tool routes and mention tokens."""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import re

from mcp_context import DIAPASON_SERVER_ID
from pascal.agent.discovery import _mention_label_slug
from pascal.api.schemas import McpToolInfo


_MENTION_IN_TEXT_RE = re.compile(r"(?:^|[\s(])@(\S+)")


def _resolve_mention_token_to_names(
    token_part: str, tool_infos: List[McpToolInfo]
) -> Optional[List[str]]:
    token = str(token_part or "").strip().lower()
    if not token:
        return None
    by_qualified = {t.name.lower(): t for t in tool_infos}
    by_native = {t.native_name.lower(): t for t in tool_infos}
    by_mention = {
        (t.mention_token or t.native_name).lower(): t
        for t in tool_infos
        if t.mention_token or t.native_name
    }
    if token in by_mention:
        return [by_mention[token].name]
    if token in by_qualified:
        return [by_qualified[token].name]
    if token in by_native:
        return [by_native[token].name]
    server_slug_to_id: Dict[str, str] = {}
    for t in tool_infos:
        if t.mcp_server.lower() == DIAPASON_SERVER_ID:
            continue
        slug = _mention_label_slug(t.mcp_label, t.mcp_server)
        server_slug_to_id.setdefault(slug, t.mcp_server)
    matched_server_id = server_slug_to_id.get(token)
    if matched_server_id:
        names = [
            t.name
            for t in tool_infos
            if t.mcp_server.lower() == matched_server_id.lower()
        ]
        return names if names else None
    return None


def _parse_tool_route(
    message: str, tool_infos: List[McpToolInfo]
) -> Tuple[str, Optional[List[str]], Optional[str], List[str]]:
    """
    Find every @token in the message (e.g. "use @docs for X and @tool for Y").
    Returns message unchanged, union of allowed tool names, scope label, unknown tokens.
    """
    raw = str(message or "")
    route_names: set[str] = set()
    route_tokens: List[str] = []
    unknown: List[str] = []
    seen: set[str] = set()

    for m in _MENTION_IN_TEXT_RE.finditer(raw):
        token_part = m.group(1)
        key = token_part.lower()
        if key in seen:
            continue
        seen.add(key)
        resolved = _resolve_mention_token_to_names(token_part, tool_infos)
        if resolved is None:
            unknown.append(token_part)
        else:
            route_tokens.append(f"@{token_part}")
            route_names.update(resolved)

    names_list = sorted(route_names) if route_names else None
    scope = ", ".join(route_tokens) if route_tokens else None
    return raw, names_list, scope, unknown