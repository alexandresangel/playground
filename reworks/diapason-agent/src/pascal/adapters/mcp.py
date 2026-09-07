"""Bounded stateless MCP JSON/SSE transport for the existing Diapason servers.

No session negotiation or automatic tool retries. Stateful MCP transports belong
behind the same port when needed; this adapter deliberately matches legacy HTTP.
"""

import json
import uuid

import httpx
from opentelemetry.propagate import inject

from pascal.tools.context import McpServerContext


class McpFailure(RuntimeError):
    """Safe error code, never a remote response or credential-bearing URL."""


class HttpMcpTransport:
    def __init__(self, config: dict, max_bytes: int, client: httpx.AsyncClient | None = None):
        self.config = config
        self.max_bytes = max_bytes
        self.client = client or httpx.AsyncClient(follow_redirects=False)

    async def request(self, server: McpServerContext, method: str, params: dict) -> dict:
        rpc_id = str(uuid.uuid4())
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": server.protocol_version,
            **server.request_headers,
        }
        inject(headers)
        timeout = float(self.config.get(server.server_id, {}).get("timeout_s", 60))
        # A plain Request avoids AsyncClient's cookie jar crossing tenant boundaries.
        request = httpx.Request(
            "POST",
            server.server_url,
            headers=headers,
            json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params},
            extensions={"timeout": httpx.Timeout(timeout).as_dict()},
        )
        try:
            response = await self.client.send(request, stream=True)
            try:
                if response.status_code >= 300:
                    raise McpFailure(f"mcp_http_{response.status_code}")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > self.max_bytes:
                        raise McpFailure("mcp_response_too_large")
                    if "text/event-stream" in response.headers.get("content-type", ""):
                        normalized = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
                        for event in normalized.split("\n\n")[:-1]:
                            lines = [
                                line[5:].lstrip()
                                for line in event.splitlines()
                                if line.startswith("data:")
                            ]
                            if not lines:
                                continue
                            try:
                                body = json.loads("\n".join(lines))
                            except ValueError:
                                continue
                            if isinstance(body, dict) and body.get("id") == rpc_id:
                                return self._result(body, rpc_id)
                return self._result(json.loads(data), rpc_id)
            finally:
                await response.aclose()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise McpFailure("mcp_transport_error") from exc

    @staticmethod
    def _result(body, rpc_id: str) -> dict:
        if not isinstance(body, dict) or body.get("id") != rpc_id:
            raise McpFailure("mcp_invalid_response")
        if body.get("error") is not None:
            raise McpFailure("mcp_rpc_error")
        result = body.get("result")
        if not isinstance(result, dict):
            raise McpFailure("mcp_invalid_result")
        return result

    async def close(self):
        await self.client.aclose()
