import httpx
from mcp.server.fastmcp import FastMCP

from pascal.adapters.mcp import HttpMcpTransport
from pascal.tools.context import McpServerContext


async def test_transport_against_real_stateless_mcp_sdk_server():
    server = FastMCP("protocol fixture", stateless_http=True, json_response=True)

    @server.tool()
    def echo(text: str) -> str:
        return text

    application = server.streamable_http_app()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=application))
    adapter = HttpMcpTransport({}, 4096, client)
    context = McpServerContext("default", "Fixture", "http://localhost:8000/mcp")
    async with server.session_manager.run():
        listing = await adapter.request(context, "tools/list", {})
        assert listing["tools"][0]["name"] == "echo"
        result = await adapter.request(
            context, "tools/call", {"name": "echo", "arguments": {"text": "hello"}}
        )
        assert result["content"][0]["text"] == "hello"
    await adapter.close()
