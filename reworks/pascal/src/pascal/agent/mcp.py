from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
import time

from mcp_context import DIAPASON_SERVER_ID, McpCluster, McpServerContext, parse_qualified_tool_name, qualify_tool_name
from mcp_rpc import TOOL_CALL_TIMEOUT_S, mcp_request as _mcp_request
from pascal.runtime import Runtime


log = logging.getLogger("diapason.chat")


def _get_server_mcp_summary(server: McpServerContext) -> str:
    tools_result = _mcp_request(server, "tools/list", {})
    raw_tools = tools_result.get("tools", [])
    tool_names = [
        qualify_tool_name(server.server_id, str(t.get("name", "unknown")))
        for t in raw_tools
        if isinstance(t, dict)
    ]

    mcp_version = None
    native_names = [t.get("name") for t in raw_tools if isinstance(t, dict)]
    if "getMcpServerVersion" in native_names:
        version_result = _mcp_request(
            server, "tools/call", {"name": "getMcpServerVersion", "arguments": {}}
        )
        content = version_result.get("content", [])
        if isinstance(content, list) and content and isinstance(content[0], dict):
            mcp_version = content[0].get("text")

    version_part = f" version {mcp_version}" if mcp_version else ""
    preview = ", ".join(tool_names[:8])
    if len(tool_names) > 8:
        preview += f", … (+{len(tool_names) - 8} more)"
    return f"[{server.label}]{version_part}: {preview or '(no tools)'}"


def _get_mcp_summary(cluster: McpCluster) -> str:
    parts: List[str] = []
    for server in cluster.servers:
        try:
            parts.append(_get_server_mcp_summary(server))
        except Exception as exc:
            parts.append(f"[{server.label}] unavailable ({exc})")
    return "MCP — " + " | ".join(parts)


def _parse_tool_arguments(args_raw: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(args_raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _tool_trace_entry(
    qualified_name: str,
    arguments: Dict[str, Any],
    duration_ms: int,
    *,
    mcp_server: str = DIAPASON_SERVER_ID,
    mcp_label: str = "Diapason",
    tool_name: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "name": qualified_name,
        "tool": tool_name or qualified_name,
        "mcp_server": mcp_server,
        "mcp_label": mcp_label,
        "arguments": arguments,
        "duration_ms": duration_ms,
    }


def _mcp_tool_timeout_s(runtime: Runtime, server: McpServerContext) -> float:
    """Per-server mcp.<id>.timeout_s, else mcp.tool_timeout_s, else 300s."""
    mcp = runtime.config.get("mcp") if isinstance(runtime.config.get("mcp"), dict) else {}
    block = mcp.get(server.server_id) if isinstance(mcp.get(server.server_id), dict) else {}
    for raw in (block.get("timeout_s"), mcp.get("tool_timeout_s"), TOOL_CALL_TIMEOUT_S):
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            return val
    return TOOL_CALL_TIMEOUT_S


def _invoke_mcp_tool(runtime: Runtime, 
    cluster: McpCluster,
    qualified_name: str,
    arguments: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    server_id, native_name = parse_qualified_tool_name(qualified_name, cluster.server_ids())
    server = cluster.get(server_id)
    if server is None:
        raise RuntimeError(f"Unknown MCP server for tool {qualified_name!r}")
    timeout_s = _mcp_tool_timeout_s(runtime, server)
    log.info(
        "mcp tool start server=%s label=%s tool=%s url=%s timeout=%.0fs",
        server.server_id,
        server.label,
        native_name,
        server.server_url,
        timeout_s,
    )
    started = time.perf_counter()
    span_cm = (
        runtime.tracer.start_as_current_span(
            "mcp.client.tools.call",
            record_exception=False,
            set_status_on_exception=False,
            attributes={
                "mcp.tool": native_name,
                "mcp.server": server.server_id,
                "mcp.label": server.label,
            },
        )
        if runtime.tracer
        else nullcontext()
    )
    with span_cm as span:
        try:
            tool_result = _mcp_request(
                server,
                "tools/call",
                {"name": native_name, "arguments": arguments},
                timeout_s=timeout_s,
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if span is not None:
                span.set_attribute("ai.outcome", "error")
                span.set_attribute("mcp.duration_ms", elapsed_ms)
            log.error(
                "mcp tool fail server=%s label=%s tool=%s url=%s elapsed=%dms err=%s",
                server.server_id,
                server.label,
                native_name,
                server.server_url,
                elapsed_ms,
                type(exc).__name__,
            )
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if span is not None:
            span.set_attribute("mcp.duration_ms", elapsed_ms)
    log.info(
        "mcp tool ok server=%s label=%s tool=%s elapsed=%dms",
        server.server_id,
        server.label,
        native_name,
        elapsed_ms,
    )
    trace_entry = _tool_trace_entry(
        qualified_name,
        arguments,
        elapsed_ms,
        mcp_server=server.server_id,
        mcp_label=server.label,
        tool_name=native_name,
    )
    return tool_result, trace_entry