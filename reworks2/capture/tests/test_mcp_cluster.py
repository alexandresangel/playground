#!/usr/bin/env python3
"""MCP config parsing."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.fernet import Fernet

from mcp_context import (
    PRIMARY_SERVER_ID,
    _parse_request_headers,
    mcp_cluster_from_request,
    parse_qualified_tool_name,
    qualify_tool_name,
)


def test_qualify_and_parse() -> None:
    assert qualify_tool_name(PRIMARY_SERVER_ID, "getBalance") == "getBalance"
    assert qualify_tool_name("docs", "search") == "docs__search"
    ids = (PRIMARY_SERVER_ID, "docs")
    assert parse_qualified_tool_name("docs__search", ids) == ("docs", "search")
    assert parse_qualified_tool_name("getBalance", ids) == (PRIMARY_SERVER_ID, "getBalance")


def test_parse_request_headers() -> None:
    headers = _parse_request_headers(
        {"headers": {"Authorization": "Bearer abc", "X-Custom": "1"}}
    )
    assert headers["Authorization"] == "Bearer abc"
    assert headers["X-Custom"] == "1"


def test_cluster_from_config() -> None:
    request = MagicMock()
    request.headers.get.side_effect = lambda h, default="": {
        "X-Diapason-Mcp-Token": "jwt",
        "X-Diapason-Mcp-Scope": "1",
        "X-Diapason-Mcp-Base-Url": "https://example/diapason",
    }.get(h, default)

    key = Fernet.generate_key().decode()
    cfg = {
        "mcp": {
            "default": {"server_url": "http://main/mcp", "config_key": key},
            "docs": {
                "server_url": "http://docs/mcp",
                "headers": {"Authorization": "Bearer docs-token"},
            },
        }
    }
    cluster = mcp_cluster_from_request(request, cfg)
    assert cluster.primary.server_id == PRIMARY_SERVER_ID
    assert cluster.primary.request_headers["Authorization"].startswith("Bearer ")
    docs = cluster.get("docs")
    assert docs is not None
    assert docs.request_headers["Authorization"] == "Bearer docs-token"


if __name__ == "__main__":
    test_qualify_and_parse()
    test_parse_request_headers()
    test_cluster_from_config()
    print("OK")
