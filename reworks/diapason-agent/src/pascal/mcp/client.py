"""One server/identity binding, using the official MCP SDK lifecycle.

Each operation opens and closes its SDK session in the same coroutine. Current
Diapason/Capture servers are stateless; no cross-turn remote session is promised.
This avoids long-lived credential caches and cross-task AnyIO cancel-scope ownership.
"""

import asyncio
from datetime import timedelta

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from opentelemetry.propagate import inject

from pascal.mcp.transport import BorrowedTransport, McpFailure
from pascal.tools.context import McpServerContext


class McpClient:
    def __init__(self, server: McpServerContext, transport, *, timeout: float, max_bytes: int):
        self.server, self.transport = server, transport
        self.timeout, self.max_bytes = timeout, max_bytes

    async def request(self, method: str, params: dict) -> dict:
        if method == "tools/list":
            message = types.ListToolsRequest(params=types.PaginatedRequestParams(**params))
            result_type = types.ListToolsResult
        elif method == "tools/call":
            message = types.CallToolRequest(params=types.CallToolRequestParams(**params))
            result_type = types.CallToolResult
        else:
            raise McpFailure("mcp_method_not_enabled")
        headers = dict(self.server.request_headers)
        inject(headers)
        # The SDK negotiates the protocol. No manual JSON-RPC IDs/SSE parser or
        # forced legacy MCP-Protocol-Version header belongs in the host.
        headers = {k: v for k, v in headers.items() if k.lower() != "mcp-protocol-version"}
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(
                    transport=BorrowedTransport(self.transport, self.max_bytes),
                    headers=headers,
                    timeout=self.timeout,
                    follow_redirects=False,
                ) as http:
                    async with streamable_http_client(
                        self.server.server_url, http_client=http
                    ) as streams:
                        async with ClientSession(
                            streams[0],
                            streams[1],
                            read_timeout_seconds=timedelta(seconds=self.timeout),
                            client_info=types.Implementation(name="pascal", version="0.1.0"),
                        ) as session:
                            await session.initialize()
                            # The public typed SDK request method avoids a second implicit
                            # tools/list and output-schema URL fetching in call_tool().
                            result = await session.send_request(
                                types.ClientRequest(message), result_type
                            )
                            return result.model_dump(by_alias=True, exclude_none=True)
        except Exception as exc:
            raise McpFailure("mcp_client_unavailable") from exc
