"""Forward the existing upload contract to Capture; no extraction or MCP execution."""

import math
import os

import httpx
from fastapi import HTTPException, Request
from starlette.responses import Response

from i18n import LOCALE_HEADER
from mcp_context import (
    DIAPASON_API_JWT_HEADER,
    DIAPASON_BASE_URL_HEADER,
    DIAPASON_SCOPE_HEADER,
    MCP_VERSION_HEADER,
)

EXTRACTION_PATH = "/api/skills/intelligence-contract"
CHAT_SESSION_HEADER = "X-Diapason-Chat-Session"
_FORWARDED_HEADERS = (
    "Authorization", "X-Diapason-User-Id", "X-Diapason-Customer-Id",
    CHAT_SESSION_HEADER, LOCALE_HEADER, DIAPASON_API_JWT_HEADER,
    DIAPASON_BASE_URL_HEADER, DIAPASON_SCOPE_HEADER, MCP_VERSION_HEADER,
    "traceparent", "tracestate",
)


def capture_enabled(config: dict) -> bool:
    block = config.get("intelligence_contract")
    return isinstance(block, dict) and block.get("enabled") is True


def _connection() -> tuple[str, float]:
    base = os.environ.get("CAPTURE_URL", "").strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Capture is not configured (CAPTURE_URL)")
    try:
        url = httpx.URL(base)
        timeout = float(os.environ.get("CAPTURE_TIMEOUT_S", "600"))
        if (url.scheme not in ("http", "https") or not url.host or url.userinfo
                or url.query or url.fragment or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError
    except (ValueError, httpx.InvalidURL) as exc:
        raise HTTPException(status_code=503, detail="Invalid Capture connection configuration") from exc
    return base, timeout


async def request_capture(request: Request, path: str, *, method: str = "GET", **kwargs) -> httpx.Response:
    base, timeout = _connection()
    headers = {name: request.headers[name] for name in _FORWARDED_HEADERS if name in request.headers}
    # Reuse the existing trace provider; never propagate arbitrary baggage or credentials.
    from opentelemetry.propagate import inject
    inject(headers)
    headers.pop("baggage", None)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            return await client.request(method, base + path, headers=headers, **kwargs)
    except httpx.TimeoutException as exc:
        # No retry: Capture may already have written the session turn.
        raise HTTPException(status_code=504, detail="Capture request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Capture service is unavailable") from exc


def public_response(upstream: httpx.Response) -> Response:
    headers = {
        name: upstream.headers[name]
        for name in ("content-type", CHAT_SESSION_HEADER, "www-authenticate", "retry-after")
        if name in upstream.headers
    }
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)
