"""Characterize the company's stateless transport; no SDK handshake or global cache."""

import json
from unittest.mock import MagicMock

import httpx
import pytest

import mcp_rpc
from mcp_context import McpServerContext


@pytest.mark.parametrize("sse", [False, True])
def test_original_json_rpc_transport_and_headers(monkeypatch, sse):
    result = {"structuredContent": {"result": {"success": True, "trade_xml": "<trade/>"}}}
    envelope = {"jsonrpc": "2.0", "id": 1, "result": result}
    response = httpx.Response(200, request=httpx.Request("POST", "https://mcp.test/mcp"),
        headers={"Content-Type": "text/event-stream" if sse else "application/json"},
        content=("data: " + json.dumps(envelope) + "\n\n") if sse else json.dumps(envelope))
    transport = MagicMock()
    transport.__enter__.return_value = transport
    transport.post.return_value = response
    constructor = MagicMock(return_value=transport)
    monkeypatch.setattr(mcp_rpc.httpx, "Client", constructor)
    server = McpServerContext("default", "Diapason", "https://mcp.test/mcp", {"Authorization": "Bearer request-scoped", "X-Company": "same"}, "company-version")
    actual = mcp_rpc.mcp_call_tool_json(server, "resolveReferences", {"view_entity": "loanDeposit", "trade_xml": "<trade/>"}, timeout_s=180)
    assert actual == {"success": True, "trade_xml": "<trade/>"}
    constructor.assert_called_once_with(timeout=180)
    transport.post.assert_called_once()
    args, kwargs = transport.post.call_args
    assert args == (server.server_url,)
    assert kwargs["headers"]["Authorization"] == "Bearer request-scoped"
    assert kwargs["headers"]["MCP-Protocol-Version"] == "company-version"
    assert kwargs["headers"]["Accept"] == "application/json, text/event-stream"
    assert kwargs["json"]["method"] == "tools/call"
    assert kwargs["json"]["params"] == {"name": "resolveReferences", "arguments": {"view_entity": "loanDeposit", "trade_xml": "<trade/>"}}


def test_result_shapes_and_existing_errors():
    assert mcp_rpc.mcp_tool_result_json({"content": [{"text": '{"answer":1}'}]}) == {"answer": 1}
    with pytest.raises(RuntimeError, match="MCP tool failed"):
        mcp_rpc.mcp_tool_result_json({"isError": True, "content": [{"text": "original error"}]})
    with pytest.raises(RuntimeError, match="must be an object"):
        mcp_rpc.mcp_tool_result_json({"content": [{"text": "[]"}]})
