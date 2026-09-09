import httpx
import pytest
from mcp.server.fastmcp import FastMCP

from pascal.mcp.host import McpHost
from pascal.tools.context import McpServerContext


@pytest.mark.parametrize("stateless", [True, False])
@pytest.mark.parametrize("json_response", [True, False])
async def test_transport_against_real_mcp_sdk_server(stateless, json_response):
    server = FastMCP("protocol fixture", stateless_http=stateless, json_response=json_response)

    @server.tool()
    def echo(text: str) -> str:
        return text

    application = server.streamable_http_app()
    client = httpx.ASGITransport(app=application)
    adapter = McpHost({}, 4096, client)
    context = McpServerContext("default", "Fixture", "http://localhost:8000/mcp")
    async with server.session_manager.run():
        listing = await adapter.request(context, "tools/list", {})
        assert listing["tools"][0]["name"] == "echo"
        result = await adapter.request(
            context, "tools/call", {"name": "echo", "arguments": {"text": "hello"}}
        )
        assert result["content"][0]["text"] == "hello"
    await adapter.close()
