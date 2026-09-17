"""resolveReferences over MCP JSON-RPC, including transport and payload errors."""

import json

import httpx
import pytest

from mcp_context import McpServerContext
from mcp_rpc import mcp_call_tool_json, mcp_tool_result_json, parse_mcp_http_body


@pytest.fixture
def server():
    return McpServerContext(
        "default", "Diapason", "https://mcp.example/mcp", {"Authorization": "Bearer encrypted"}
    )


@pytest.mark.parametrize(
    "result",
    [
        {"structuredContent": {"success": True, "trade_xml": "<trade/>"}},
        {"structuredContent": {"result": {"success": True, "trade_xml": "<trade/>"}}},
        {"content": [{"type": "text", "text": '{"success": true, "trade_xml": "<trade/>"}'}]},
    ],
    ids=["structured", "nested-structured", "text-json"],
)
def test_tool_result_accepts_supported_mcp_encodings(result):
    assert mcp_tool_result_json(result) == {"success": True, "trade_xml": "<trade/>"}


@pytest.mark.parametrize(
    "result,message",
    [
        ({"isError": True, "content": [{"text": "unavailable"}]}, "MCP tool failed"),
        ({}, "no content"),
        ({"content": "wrong"}, "no content"),
        ({"content": [{}]}, "missing text"),
        ({"content": [{"text": "Error executing tool resolveReferences"}]}, "Error executing tool"),
        ({"content": [{"text": "not JSON"}]}, "did not return JSON"),
        ({"content": [{"text": "[]"}]}, "must be an object"),
    ],
)
def test_invalid_tool_results_raise_runtime_errors(result, message):
    with pytest.raises(RuntimeError, match=message):
        mcp_tool_result_json(result)


@pytest.mark.parametrize("encoding", ["json", "sse", "unlabelled-json"])
def test_resolve_references_request_and_response_over_mock_http(server, mcp_transport, encoding):
    calls = []

    def handle(request):
        calls.append(request)
        body = {
            "jsonrpc": "2.0",
            "id": json.loads(request.content)["id"],
            "result": {"structuredContent": {"success": True, "trade_xml": "<trade/>"}},
        }
        if encoding == "sse":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text=": keepalive\n\ndata: not-json\n\ndata: " + json.dumps(body) + "\n\n",
            )
        if encoding == "unlabelled-json":
            return httpx.Response(200, text=json.dumps(body))
        return httpx.Response(200, json=body)

    factory = mcp_transport(handle)
    arguments = {"view_entity": "loanDeposit", "trade_xml": "<trade/>"}
    result = mcp_call_tool_json(server, "resolveReferences", arguments, timeout_s=180)
    assert result == {"success": True, "trade_xml": "<trade/>"}
    factory.assert_called_once_with(timeout=180)
    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url) == server.server_url
    assert request.headers["Authorization"] == "Bearer encrypted"
    assert request.headers["MCP-Protocol-Version"] == server.protocol_version
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Accept"] == "application/json, text/event-stream"
    payload = json.loads(request.content)
    assert isinstance(payload.pop("id"), int)
    assert payload == {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "resolveReferences", "arguments": arguments},
    }


@pytest.mark.parametrize(
    "failure,message",
    [
        ("timeout", "timed out after 180s"),
        ("connection", "HTTP error"),
        ("status", "HTTP error"),
        ("rpc", "MCP error"),
        ("missing-result", "missing result"),
    ],
)
def test_transport_and_rpc_failures_propagate(server, mcp_transport, failure, message):
    def handle(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if failure == "connection":
            raise httpx.ConnectError("unreachable", request=request)
        if failure == "status":
            return httpx.Response(503)
        if failure == "rpc":
            return httpx.Response(200, json={"error": {"code": -32603, "message": "failed"}})
        return httpx.Response(200, json={"jsonrpc": "2.0"})

    mcp_transport(handle)
    with pytest.raises(RuntimeError, match=message):
        mcp_call_tool_json(server, "resolveReferences", {}, timeout_s=180)


@pytest.mark.parametrize(
    "content_type,text,message",
    [
        ("application/json", "[]", "root must be an object"),
        ("text/event-stream", ": keepalive\n\ndata: not-json\n\n", "no JSON-RPC object"),
        ("text/html", "<html>error</html>", "Unexpected MCP Content-Type"),
    ],
)
def test_unusable_http_bodies_are_rejected(content_type, text, message):
    with pytest.raises(RuntimeError, match=message):
        parse_mcp_http_body(httpx.Response(200, headers={"Content-Type": content_type}, text=text))
