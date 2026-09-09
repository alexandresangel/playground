"""Pascal is the MCP host: it selects server-scoped clients, never grants tool authority."""

import httpx

from pascal.mcp.client import McpClient
from pascal.tools.context import McpServerContext


class McpHost:
    def __init__(
        self, config: dict, max_bytes: int, http_transport: httpx.AsyncBaseTransport | None = None
    ):
        self.config, self.max_bytes = config, max_bytes
        self.http_transport = http_transport or httpx.AsyncHTTPTransport(retries=0)

    def client(self, server: McpServerContext) -> McpClient:
        return McpClient(
            server,
            self.http_transport,
            timeout=float(self.config.get(server.server_id, {}).get("timeout_s", 60)),
            max_bytes=self.max_bytes,
        )

    async def request(self, server: McpServerContext, method: str, params: dict) -> dict:
        return await self.client(server).request(method, params)

    async def close(self):
        await self.http_transport.aclose()
