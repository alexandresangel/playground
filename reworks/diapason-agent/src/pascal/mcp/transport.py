"""HTTP connection pooling with a bounded response stream, not a protocol parser."""

import json

import httpx


class McpFailure(RuntimeError):
    """An operational code; remote messages and credential-bearing URLs stay private."""


class BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, maximum: int):
        self.stream, self.maximum = stream, maximum

    async def __aiter__(self):
        total = 0
        async for chunk in self.stream:
            total += len(chunk)
            if total > self.maximum:
                raise McpFailure("mcp_response_too_large")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class BoundedResponse(httpx.Response):
    maximum: int

    async def aiter_bytes(self, chunk_size=None):
        total = 0
        async for chunk in super().aiter_bytes(chunk_size):
            # Bound decoded data too (a small gzip body can expand substantially).
            total += len(chunk)
            if total > self.maximum:
                raise McpFailure("mcp_response_too_large")
            yield chunk

    async def aread(self):
        content = await super().aread()
        # Reject even an ambiguous error+result JSON envelope; the SDK's typed
        # response union otherwise accepts the result and ignores the error field.
        if content and "application/json" in self.headers.get("content-type", ""):
            body = json.loads(content)
            if isinstance(body, dict) and body.get("error") is not None:
                raise McpFailure("mcp_rpc_error")
        return content


class BorrowedTransport(httpx.AsyncBaseTransport):
    """Each client borrows the host's sockets, never another identity's cookies/session."""

    def __init__(self, transport: httpx.AsyncBaseTransport, maximum: int):
        self.transport, self.maximum = transport, maximum

    async def handle_async_request(self, request):
        response = await self.transport.handle_async_request(request)
        bounded = BoundedResponse(
            response.status_code,
            headers=response.headers,
            stream=BoundedStream(response.stream, self.maximum),
            extensions=response.extensions,
        )
        bounded.maximum = self.maximum
        return bounded

    async def aclose(self):
        # McpHost owns this pool. A scoped SDK client must not close other clients' sockets.
        pass
