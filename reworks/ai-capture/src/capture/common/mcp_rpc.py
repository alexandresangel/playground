"""JSON-RPC helpers for Diapason MCP streamable HTTP."""

from __future__ import annotations

import itertools
import json
from contextlib import contextmanager
from urllib.parse import urlparse
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from typing import Any, Dict, Optional

import httpx

from mcp_context import McpServerContext

_REQUEST_COUNTER = itertools.count(1)

# tools/list and handshake; tools/call uses a longer default (docs MCP can be slow).
DEFAULT_TIMEOUT_S = 60.0
TOOL_CALL_TIMEOUT_S = 300.0


def parse_mcp_http_body(response: httpx.Response) -> Dict[str, Any]:
    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise RuntimeError("MCP JSON response root must be an object.")
        return parsed

    if "text/event-stream" in content_type:
        text = response.text
        for block in text.split("\n\n"):
            for line in block.split("\n"):
                line_s = line.strip()
                if not line_s.startswith("data:"):
                    continue
                raw = line_s[5:].strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                    return obj
        raise RuntimeError(f"MCP SSE response contained no JSON-RPC object (preview): {text[:800]!r}")

    try:
        fallback = response.json()
        if isinstance(fallback, dict):
            return fallback
    except json.JSONDecodeError:
        pass
    raise RuntimeError(
        f"Unexpected MCP Content-Type {content_type!r}; body preview: {response.text[:800]!r}"
    )


def mcp_http_headers(server: McpServerContext) -> Dict[str, str]:
    headers = dict(server.request_headers)
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json, text/event-stream")
    headers.setdefault("MCP-Protocol-Version", server.protocol_version)
    return headers


@contextmanager
def _rpc_span(server: McpServerContext, method: str, params: Optional[Dict[str, Any]]):
    host = urlparse(server.server_url)
    attributes = {
        "rpc.system": "jsonrpc", "rpc.method": method,
        "mcp.server.id": server.server_id, "server.address": host.hostname or "",
    }
    if method == "tools/call" and params:
        attributes["gen_ai.tool.name"] = str(params.get("name") or "")
    with trace.get_tracer("capture").start_as_current_span(
        "mcp.request", kind=SpanKind.CLIENT, attributes=attributes,
        record_exception=False, set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR))
            span.set_attribute("error.type", type(exc).__name__)
            raise


def mcp_request(
    server: McpServerContext,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    with _rpc_span(server, method, params) as span:
        request_id = next(_REQUEST_COUNTER)
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params

        tool_name = ""
        if method == "tools/call" and isinstance(params, dict):
            tool_name = str(params.get("name") or "").strip()

        headers = mcp_http_headers(server)
        try:
            from opentelemetry import propagate

            propagate.inject(headers)
        except Exception:
            pass

        try:
            with httpx.Client(timeout=timeout_s) as client:
                response = client.post(
                    server.server_url,
                    headers=headers,
                    json=payload,
                )
                span.set_attribute("http.response.status_code", response.status_code)
                response.raise_for_status()
                body = parse_mcp_http_body(response)
        except httpx.TimeoutException as exc:
            detail = f"tool={tool_name} " if tool_name else ""
            raise RuntimeError(
                f"MCP {method} timed out after {timeout_s:.0f}s "
                f"({detail}server={server.server_id} label={server.label!r} url={server.server_url})"
            ) from exc
        except httpx.HTTPError as exc:
            detail = f"tool={tool_name} " if tool_name else ""
            raise RuntimeError(
                f"MCP {method} HTTP error "
                f"({detail}server={server.server_id} label={server.label!r} url={server.server_url}): {exc}"
            ) from exc

        if "error" in body:
            raise RuntimeError(f"MCP error for {method}: {body['error']}")
        if "result" not in body:
            raise RuntimeError(f"MCP response missing result for {method}")
        result = body["result"]
        if isinstance(result, dict) and result.get("isError"):
            span.set_status(Status(StatusCode.ERROR))
            span.set_attribute("error.type", "McpToolError")
        return result


def mcp_tool_result_json(result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("isError"):
        content = result.get("content", [])
        text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
        raise RuntimeError(f"MCP tool failed: {text or result!r}")

    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        payload = structured.get("result", structured)
        if isinstance(payload, dict):
            return payload

    content = result.get("content", [])
    if not isinstance(content, list) or not content or not isinstance(content[0], dict):
        raise RuntimeError(f"MCP tool returned no content: {result!r}")
    text = content[0].get("text")
    if text is None:
        raise RuntimeError(f"MCP tool content missing text: {result!r}")
    text = str(text)
    if text.startswith("Error executing tool"):
        raise RuntimeError(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"MCP tool did not return JSON: {text[:500]!r}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"MCP tool JSON must be an object: {text[:500]!r}")
    return parsed


def mcp_call_tool_json(
    server: McpServerContext,
    name: str,
    arguments: Dict[str, Any],
    *,
    timeout_s: float = TOOL_CALL_TIMEOUT_S,
) -> Dict[str, Any]:
    result = mcp_request(
        server,
        "tools/call",
        {"name": name, "arguments": arguments},
        timeout_s=timeout_s,
    )
    return mcp_tool_result_json(result)