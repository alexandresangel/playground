"""Discover and filter tools per request through the existing company MCP interface."""

from __future__ import annotations
from mcp_context import DIAPASON_SERVER_ID, McpCluster, McpServerContext, qualify_tool_name
from mcp_rpc import mcp_request as _mcp_request
from pascal.api.schemas import McpServerTools, McpToolInfo, McpToolsListResponse
from pascal.runtime import Runtime
from tool_audience import audience_from_raw, is_chat_api_listed, is_tool_mentionable
from typing import Any, Dict, List, Optional
import logging
import re

log = logging.getLogger("diapason.chat")


def _mention_exclude_rules(runtime: Runtime) -> List[str]:
    ui = runtime.config.get("ui") if isinstance(runtime.config.get("ui"), dict) else {}
    raw = ui.get("mention_exclude_tools", [])
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _mention_label_slug(label: str, server_id: str) -> str:
    """Slug from mcp.{id}.label in config (e.g. Docs -> docs)."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(label or "").strip().lower()).strip("_")
    return slug or str(server_id or "").strip().lower()


def _mention_token_for_tool(server: McpServerContext, native_name: str) -> str:
    native = native_name.strip()
    if server.server_id == DIAPASON_SERVER_ID:
        return native
    prefix = _mention_label_slug(server.label, server.server_id)
    return f"{prefix}.{native}"


def _tool_info_from_raw(runtime: Runtime, server: McpServerContext, raw: Dict[str, Any]) -> Optional[McpToolInfo]:
    native_name = raw.get("name")
    if not isinstance(native_name, str) or not native_name:
        return None
    qualified = qualify_tool_name(server.server_id, native_name)
    description = raw.get("description")
    if not isinstance(description, str) or not description.strip():
        description = f"MCP tool '{native_name}'."
    mention_token = _mention_token_for_tool(server, native_name)
    audience = audience_from_raw(raw)
    return McpToolInfo(
        name=qualified,
        native_name=native_name,
        mcp_server=server.server_id,
        mcp_label=server.label,
        description=description,
        input_schema=_normalize_tool_schema(raw.get("inputSchema")),
        audience=audience,
        mentionable=is_tool_mentionable(
            native_name, qualified, audience, _mention_exclude_rules(runtime)
        ),
        mention_token=mention_token,
    )


def _list_tools_for_server(runtime: Runtime, server: McpServerContext, *, for_chat_api: bool = False) -> McpServerTools:
    try:
        tools_result = _mcp_request(server, "tools/list", {})
        raw_tools = tools_result.get("tools", [])
        tools: List[McpToolInfo] = []
        if isinstance(raw_tools, list):
            for raw in raw_tools:
                if isinstance(raw, dict):
                    if for_chat_api and not is_chat_api_listed(audience_from_raw(raw)):
                        continue
                    info = _tool_info_from_raw(runtime, server, raw)
                    if info is not None:
                        tools.append(info)
        return McpServerTools(
            server_id=server.server_id,
            label=server.label,
            mention_prefix=_mention_label_slug(server.label, server.server_id),
            server_url=server.server_url,
            ok=True,
            tools=tools,
        )
    except Exception as exc:
        log.warning("tools/list failed for MCP server %s: %s", server.server_id, exc)
        return McpServerTools(
            server_id=server.server_id,
            label=server.label,
            mention_prefix=_mention_label_slug(server.label, server.server_id),
            server_url=server.server_url,
            ok=False,
            error=str(exc),
            tools=[],
        )


def _list_mcp_tools(runtime: Runtime, cluster: McpCluster, *, for_chat_api: bool = False) -> McpToolsListResponse:
    servers: List[McpServerTools] = []
    flat: List[McpToolInfo] = []
    for server in cluster.servers:
        entry = _list_tools_for_server(runtime, server, for_chat_api=for_chat_api)
        servers.append(entry)
        if entry.ok:
            flat.extend(entry.tools)
    return McpToolsListResponse(servers=servers, tools=flat)


def _get_server_tool_definitions(runtime: Runtime, server: McpServerContext) -> List[Dict[str, Any]]:
    entry = _list_tools_for_server(runtime, server, for_chat_api=True)
    if not entry.ok:
        return []
    tool_defs: List[Dict[str, Any]] = []
    for info in entry.tools:
        description = info.description
        if info.mcp_server != DIAPASON_SERVER_ID:
            description = f"[{info.mcp_label}] {description}"
        tool_defs.append(
            {
                "type": "function",
                "function": {
                    "name": info.name,
                    "description": description,
                    "parameters": info.input_schema,
                },
            }
        )
    return tool_defs


def _get_mcp_tool_definitions(runtime: Runtime, cluster: McpCluster) -> List[Dict[str, Any]]:
    tool_defs: List[Dict[str, Any]] = []
    for server in cluster.servers:
        tool_defs.extend(_get_server_tool_definitions(runtime, server))
    return tool_defs


def _filter_tool_definitions(
    tool_defs: List[Dict[str, Any]], allowed_tool_names: Optional[List[str]]
) -> List[Dict[str, Any]]:
    if not allowed_tool_names:
        return tool_defs
    allowed = {name.strip() for name in allowed_tool_names if isinstance(name, str) and name.strip()}
    if not allowed:
        return []
    out: List[Dict[str, Any]] = []
    for td in tool_defs:
        fn = td.get("function") if isinstance(td, dict) else None
        name = fn.get("name") if isinstance(fn, dict) else None
        if isinstance(name, str) and name in allowed:
            out.append(td)
    return out


def _normalize_tool_schema(raw_schema: Any) -> Dict[str, Any]:
    if isinstance(raw_schema, dict) and raw_schema.get("type") == "object":
        return raw_schema
    if isinstance(raw_schema, dict):
        schema = dict(raw_schema)
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        return schema
    return {"type": "object", "properties": {}}
