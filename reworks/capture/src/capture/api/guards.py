"""ASGI guards without BaseHTTPMiddleware, preserving streaming cancellation semantics."""

import re
import uuid

from fastapi import HTTPException
from starlette.responses import JSONResponse


class RequestGuards:
    def __init__(self, app, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", request_id):
            request_id = str(uuid.uuid4())
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_body_bytes:
                    raise HTTPException(413, "Request body too large")
            return message

        async def response_send(message):
            if message["type"] == "http.response.start":
                outgoing = list(message.get("headers", []))
                outgoing.extend(
                    [
                        (b"x-request-id", request_id.encode()),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
                if scope["path"].startswith(("/api/", "/mcp")):
                    outgoing = [(k, v) for k, v in outgoing if k.lower() != b"cache-control"]
                    outgoing.append((b"cache-control", b"no-store"))
                message = {**message, "headers": outgoing}
            await send(message)

        try:
            size = int(headers.get(b"content-length", b"0"))
        except ValueError:
            size = self.max_body_bytes + 1
        if size < 0 or size > self.max_body_bytes:
            return await JSONResponse({"detail": "Request body too large"}, status_code=413)(
                scope, receive, response_send
            )
        await self.app(scope, bounded_receive, response_send)
