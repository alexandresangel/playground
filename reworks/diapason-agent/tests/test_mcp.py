import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from conftest import FakeMcp
from cryptography.fernet import Fernet
from starlette.requests import Request

from pascal.adapters.mcp import HttpMcpTransport, McpFailure
from pascal.config import AgentLimits
from pascal.tools.context import McpCluster, McpServerContext, mcp_from_request
from pascal.tools.registry import ToolRegistry
from pascal.tools.routing import RouteError, route


def as_request(headers):
    return Request(
        {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
    )


def test_fernet_legacy_payload_and_stable_tenant_cache_key(config, headers):
    request = as_request(headers)
    first, second = mcp_from_request(request, config), mcp_from_request(request, config)
    assert (
        first.primary.request_headers["Authorization"]
        != second.primary.request_headers["Authorization"]
    )
    token = first.primary.request_headers["Authorization"].split()[1]
    assert json.loads(Fernet(config["mcp"]["default"]["config_key"]).decrypt(token.encode())) == {
        "base_url": "https://diapason.example",
        "scope": 5,
        "api_token": "API-TOKEN",
    }
    registry = ToolRegistry(FakeMcp(), AgentLimits(), [])
    assert registry.key("demo/12/7", first.primary) == registry.key("demo/12/7", second.primary)
    assert registry.key("demo/12/8", first.primary) != registry.key("demo/12/7", first.primary)
    changed = mcp_from_request(as_request(headers | {"X-Diapason-Mcp-Token": "OTHER"}), config)
    assert registry.key("demo/12/7", first.primary) != registry.key("demo/12/7", changed.primary)


def test_dynamic_capture_forwarding_is_explicit_not_broadcast(config, headers):
    config["mcp"]["docs"] = {
        "server_url": "https://docs.example/mcp",
        "headers": {"Authorization": "Bearer docs"},
    }
    config["mcp"]["capture"] = {
        "server_url": "https://capture.example/mcp",
        "forward_diapason_identity": True,
    }
    cluster = mcp_from_request(as_request(headers), config)
    assert cluster.get("docs").request_headers == {"Authorization": "Bearer docs"}
    capture = cluster.get("capture").request_headers
    assert capture["Authorization"] == headers["Authorization"]
    assert capture["X-Diapason-Mcp-Token"] == "API-TOKEN"
    assert capture["X-Diapason-Customer-Id"] == "12"


async def test_discovery_dedup_ttl_bound_and_scope_isolation(identity):
    transport = FakeMcp()
    registry = ToolRegistry(transport, AgentLimits(catalogue_max_entries=2), [])
    await asyncio.gather(*(registry.discover(identity.mcp, identity.scope_path) for _ in range(5)))
    assert len(transport.requests) == 1
    await registry.discover(identity.mcp, "another/tenant/user")
    assert len(transport.requests) == 2
    await registry.discover(identity.mcp, "third/tenant/user")
    assert len(registry.cache) == 2
    for key, (_, rows) in list(registry.cache.items()):
        registry.cache[key] = (0, rows)
    await registry.discover(identity.mcp, "third/tenant/user")
    assert len(transport.requests) == 4


@pytest.mark.parametrize("fault", [None, "cycle", "pages", "rows"])
async def test_catalogue_pagination_and_bounds(identity, fault):
    class PagedMcp(FakeMcp):
        async def request(self, server, method, params):
            self.requests.append((server, method, params))
            page_number = len(self.requests)
            if fault == "rows":
                return {"tools": [{"name": "balance"}] * 501}
            result = {"tools": [{"name": f"balance_{page_number}"}]}
            if fault == "cycle":
                result["nextCursor"] = "repeat"
            elif fault == "pages" or page_number == 1:
                result["nextCursor"] = str(page_number)
            return result

    transport = PagedMcp()
    registry = ToolRegistry(transport, AgentLimits(), [])
    catalogue = await registry.discover(identity.mcp, identity.scope_path)
    if fault is None:
        assert [tool.name for tool in catalogue.tools] == ["balance_1", "balance_2"]
        assert transport.requests[1][2] == {"cursor": "1"}
        assert catalogue.servers[0]["ok"] is True
    else:
        assert catalogue.tools == []
        assert catalogue.servers[0]["ok"] is False
        assert registry.cache == {}
        assert len(transport.requests) <= 20


async def test_hidden_tools_ambiguity_and_unknown_mentions(identity):
    transport = FakeMcp(
        rows=[
            {"name": "balance"},
            {"name": "getMcpVersion"},
            {"name": "private", "_meta": {"audience": "technical"}},
        ]
    )
    registry = ToolRegistry(transport, AgentLimits(), [])
    cluster = McpCluster(
        (*identity.mcp.servers, McpServerContext("docs", "Docs", "https://docs/mcp"))
    )
    catalogue = await registry.discover(cluster, identity.scope_path)
    assert [t.name for t in catalogue.tools] == ["balance", "docs__balance"]
    assert route("Email me at a@b.com and ask @colleague", catalogue)[0].endswith("@colleague")
    assert [t.name for t in route("@docs.balance question", catalogue)[1]] == ["docs__balance"]
    assert [t.name for t in route("/docs question", catalogue)[1]] == ["docs__balance"]
    with pytest.raises(RouteError, match="Ambiguous"):
        route("@balance question", catalogue)
    catalogue.servers[1]["ok"] = False
    with pytest.raises(RouteError, match="unavailable"):
        route("@docs question", catalogue)


@pytest.mark.parametrize("sse", [False, True])
async def test_json_and_sse_transport_no_cookie_leak(sse):
    seen = []

    async def responder(request):
        seen.append(request)
        body = json.loads(request.content)
        result = {"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}}
        headers = {"set-cookie": "session=must-not-leak; Path=/"}
        if sse:
            return httpx.Response(
                200,
                content="data: " + json.dumps(result) + "\n\n",
                headers=headers | {"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=result, headers=headers)

    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    adapter = HttpMcpTransport({}, 2048, client)
    server = McpServerContext(
        "default", "Diapason", "https://mcp.example/mcp", {"Authorization": "Bearer A"}
    )
    assert await adapter.request(server, "tools/list", {}) == {"tools": []}
    await adapter.request(
        replace(server, request_headers={"Authorization": "Bearer B"}), "tools/list", {}
    )
    assert seen[0].headers["authorization"] == "Bearer A"
    assert seen[1].headers["authorization"] == "Bearer B"
    assert "cookie" not in seen[1].headers
    assert seen[0].headers["MCP-Protocol-Version"] == "2024-11-05"
    await adapter.close()


@pytest.mark.parametrize("kind", ["id", "size", "status", "rpc"])
async def test_transport_rejects_invalid_or_large_responses(kind):
    async def responder(request):
        body = json.loads(request.content)
        result = {"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}}
        if kind == "id":
            result["id"] = "not-the-request"
        if kind == "size":
            result["result"]["large"] = "secret" * 1000
        if kind == "rpc":
            result["error"] = {"message": "SECRET"}
        return httpx.Response(503 if kind == "status" else 200, json=result)

    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    adapter = HttpMcpTransport({}, 1024, client)
    with pytest.raises(McpFailure) as exc:
        await adapter.request(McpServerContext("default", "D", "https://mcp/mcp"), "tools/list", {})
    assert "secret" not in str(exc.value).lower()
    await adapter.close()
