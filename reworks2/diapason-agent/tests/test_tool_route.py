#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from pascal.api.schemas import McpToolInfo
    from pascal.agent.routing import _parse_tool_route
except ModuleNotFoundError as exc:
    raise SystemExit(f"Skip: install chat deps ({exc})") from exc


def _tool(
    name: str,
    native: str,
    server: str = "docs",
    mention_token: str = "",
) -> McpToolInfo:
    return McpToolInfo(
        name=name,
        native_name=native,
        mcp_server=server,
        mcp_label="Docs",
        description="",
        input_schema={},
        mention_token=mention_token or native,
    )


def test_inline_two_tools() -> None:
    tools = [
        _tool("docs__search", "search", mention_token="docs.search"),
        _tool("docs__ask", "ask_docs", mention_token="docs.ask_docs"),
    ]
    msg = "Use @docs.search for lookup and @docs.ask_docs for prose."
    text, names, scope, unknown = _parse_tool_route(msg, tools)
    assert text == msg
    assert unknown == []
    assert names is not None and len(names) == 2
    assert "docs__search" in names and "docs__ask" in names
    assert "@docs.search" in scope and "@docs.ask_docs" in scope


def test_server_scope_plus_tool() -> None:
    tools = [
        _tool("docs__search", "search", mention_token="docs.search"),
        _tool("docs__ask", "ask_docs", mention_token="docs.ask_docs"),
    ]
    msg = "@docs then @docs.search please"
    _, names, _, unknown = _parse_tool_route(msg, tools)
    assert unknown == []
    assert names is not None
    assert len(names) == 2


def test_unknown_token() -> None:
    tools = [_tool("docs__search", "search", mention_token="docs.search")]
    _, _, _, unknown = _parse_tool_route("try @nope here", tools)
    assert unknown == ["nope"]


def test_no_mentions() -> None:
    tools = [_tool("docs__search", "search")]
    _, names, scope, unknown = _parse_tool_route("hello", tools)
    assert names is None and scope is None and unknown == []
