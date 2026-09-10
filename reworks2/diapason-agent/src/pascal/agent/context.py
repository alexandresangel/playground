"""Prepare the existing system prompt, history, locale and request context."""

from __future__ import annotations
from datetime import datetime
from dia_jwt.fastapi import Identity
from fastapi import HTTPException
from i18n import DEFAULT_LOCALE, locale_llm_instruction
from pascal.agent.discovery import _list_mcp_tools
from pascal.agent.mcp import _get_mcp_summary
from pascal.agent.routing import _parse_tool_route
from pascal.api.schemas import ChatRequest
from pascal.runtime import Runtime, _resolve_session_id
from prompt_loader import get_system_prompt
from settings import assistant_identity_llm_block
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _temporal_context_block(runtime: Runtime, client_timezone: Optional[str] = None) -> str:
    """
    Inject real-world date/time so the model does not rely on stale training cut-off.
    Prefer browser zone via client_timezone; else context.timezone in config.json; else UTC.
    """
    ctx = runtime.config.get("context") if isinstance(runtime.config.get("context"), dict) else {}
    configured = str(ctx.get("timezone", "UTC") or "UTC")
    tz_name = (client_timezone or configured or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz_name = str(configured or "UTC").strip() or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz_name = "UTC"
            tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    return (
        "\n\n---\n**Current date and time (authoritative — use for \"today\", \"now\", and relative ranges):**\n"
        f"- IANA time zone: `{tz_name}`\n"
        f"- **Calendar date:** {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})\n"
        f"- **Local time:** {now.strftime('%H:%M:%S')}\n"
        f"- ISO-8601: `{now.isoformat(timespec='seconds')}`\n"
        "When calling Diapason tools, map \"today\" to the calendar date above unless the user specifies otherwise.\n"
    )


def _compose_llm_messages(runtime: Runtime, 
    session_id: str,
    scope: str,
    user_message: str,
    mcp_summary: str,
    client_timezone: Optional[str] = None,
    locale: str = DEFAULT_LOCALE,
) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                get_system_prompt()
                + assistant_identity_llm_block(runtime.config)
                + _temporal_context_block(runtime, client_timezone)
                + locale_llm_instruction(locale)
                + "\nYou can call tools when needed. Use this live MCP context:\n"
                + mcp_summary
            ),
        },
    ]
    for turn in runtime.sessions.get_turns(session_id, scope):
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def _prepare_chat_context(runtime: Runtime, 
    req: ChatRequest,
    identity: Identity,
    *,
    locale: str = DEFAULT_LOCALE,
) -> tuple[str, List[Dict[str, Any]], str, Optional[List[str]], Optional[str], str]:
    route_names: Optional[List[str]] = None
    route_token: Optional[str] = None
    user_message = req.message
    try:
        route_listing = _list_mcp_tools(runtime, identity.mcp, for_chat_api=True)
        user_message, route_names, route_token, unknown_routes = _parse_tool_route(
            req.message, route_listing.tools
        )
        if unknown_routes:
            examples = sorted(
                {
                    (t.mention_token or t.native_name)
                    for t in route_listing.tools
                    if (t.mention_token or t.native_name)
                }
            )[:12]
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown @tool route: {', '.join(unknown_routes[:8])}. "
                    f"Available examples: {', '.join(examples)}"
                ),
            )
    except HTTPException:
        raise
    except Exception:
        route_names = None
        route_token = None

    try:
        mcp_summary = _get_mcp_summary(identity.mcp)
    except Exception as exc:
        mcp_summary = f"MCP connection failed: {exc}"
    if route_token:
        mcp_summary += f" | Routed tool scope: {route_token}"
    session_id = _resolve_session_id(runtime, identity.scope_path, req.session_id)
    messages = _compose_llm_messages(runtime, 
        session_id,
        identity.scope_path,
        user_message,
        mcp_summary,
        client_timezone=req.client_timezone,
        locale=locale,
    )
    return session_id, messages, mcp_summary, route_names, route_token, user_message
