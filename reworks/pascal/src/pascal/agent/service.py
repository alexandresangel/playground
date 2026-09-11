from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Dict, Iterator, List, Optional

from dia_jwt.fastapi import Identity
from i18n import DEFAULT_LOCALE
from mcp_context import McpCluster
from pascal.agent.charts import _looks_like_chart_request, _sample_chart_spec
from pascal.agent.context import _prepare_chat_context
from pascal.agent.discovery import _filter_tool_definitions, _get_mcp_tool_definitions
from pascal.agent.mcp import _invoke_mcp_tool, _parse_tool_arguments
from pascal.agent.graph import run_chat, stream_chat
from pascal.api.schemas import ChatRequest, ChatResponse
from pascal.observability.http import _emit_chat_observability, _usage_payload
from pascal.runtime import Runtime


def _call_azure_openai_with_mcp_tools(runtime: Runtime, 
    messages: List[Dict[str, Any]],
    cluster: McpCluster,
    allowed_tool_names: Optional[List[str]] = None,
    *,
    locale: str = DEFAULT_LOCALE,
) -> Optional[Dict[str, Any]]:
    azure = runtime.azure_client()
    if azure is None:
        return None
    try:
        return run_chat(messages, **_chat_dependencies(runtime, azure, cluster, allowed_tool_names, locale))
    finally:
        azure["client"].close()


def _chat_dependencies(runtime: Runtime, azure, cluster, allowed_tool_names, locale) -> Dict[str, Any]:
    ao = runtime.config.get("azure_openai") if isinstance(runtime.config.get("azure_openai"), dict) else {}
    max_rounds_raw = str(ao.get("max_tool_rounds", 4))
    max_rounds = int(max_rounds_raw or "4")
    tools = _filter_tool_definitions(_get_mcp_tool_definitions(runtime, cluster), allowed_tool_names)
    return {
        "client": azure["client"], "deployment": azure["deployment"],
        "max_rounds": max_rounds, "tools": tools,
        "allowed_tool_names": allowed_tool_names, "locale": locale,
        "invoke_tool": lambda name, arguments: _invoke_mcp_tool(runtime, cluster, name, arguments),
        "parse_arguments": _parse_tool_arguments,
    }


def _iter_chat_stream_events(runtime: Runtime, 
    messages: List[Dict[str, Any]],
    user_message: str,
    session_id: str,
    mcp_summary: str,
    cluster: McpCluster,
    client_timezone: Optional[str] = None,
    allowed_tool_names: Optional[List[str]] = None,
    *,
    locale: str = DEFAULT_LOCALE,
) -> Iterator[Dict[str, Any]]:
    azure = runtime.azure_client()
    if azure is None:
        fallback = (
            "Azure credentials not set. Returning MCP connectivity summary instead.\n\n"
            + mcp_summary
        )
        yield {"type": "delta", "content": fallback}
        done: Dict[str, Any] = {
            "type": "done",
            "mode": "mcp-http",
            "session_id": session_id,
            "tool_trace": [],
            "sources": [],
            "usage": {},
            "chart_spec": None,
            "chart_reason": None,
        }
        if _looks_like_chart_request(user_message):
            done["chart_spec"] = _sample_chart_spec()
            done["chart_reason"] = (
                "PoC attaches a sample Vega-Lite chart when the message looks visualization-oriented."
            )
        yield done
        return

    result: Dict[str, Any] = {}
    try:
        for event in stream_chat(messages, **_chat_dependencies(runtime, azure, cluster, allowed_tool_names, locale)):
            if event["type"] == "workflow_result":
                result = event["result"]
            else:
                yield event
    finally:
        azure["client"].close()

    trace = result["tool_trace"]
    sources = result["sources"]
    usage_acc = result["usage"]
    done_payload: Dict[str, Any] = {
        "type": "done",
        "mode": "mcp-http+azure-tool-calling",
        "session_id": session_id,
        "tool_trace": trace,
        "sources": sources,
        "usage": usage_acc,
        "chart_spec": None,
        "chart_reason": None,
    }
    if _looks_like_chart_request(user_message):
        done_payload["chart_spec"] = _sample_chart_spec()
        done_payload["chart_reason"] = (
            "PoC attaches a sample Vega-Lite chart when the message looks visualization-oriented."
        )
    yield done_payload


def _build_response(runtime: Runtime, 
    req: ChatRequest, identity: Identity, *, locale: str = DEFAULT_LOCALE
) -> ChatResponse:
    session_id, messages, mcp_summary, route_names, _route_token, user_message = _prepare_chat_context(runtime, 
        req, identity, locale=locale
    )
    loc = locale
    span_cm = (
        runtime.tracer.start_as_current_span("chat.completion", record_exception=False, set_status_on_exception=False)
        if runtime.tracer
        else nullcontext()
    )
    with span_cm as span:
        llm_result = _call_azure_openai_with_mcp_tools(runtime, 
            messages, identity.mcp, route_names, locale=loc
        )
        tool_trace: List[Dict[str, Any]] = []
        sources: List[Dict[str, str]] = []
        usage: Dict[str, Any] = {}
        if llm_result is None:
            llm_answer = (
                "Azure credentials not set. Returning MCP connectivity summary instead.\n\n"
                + mcp_summary
            )
        else:
            llm_answer = str(llm_result.get("answer", ""))
            raw_trace = llm_result.get("tool_trace", [])
            if isinstance(raw_trace, list):
                tool_trace = [t for t in raw_trace if isinstance(t, dict)]
            raw_sources = llm_result.get("sources", [])
            if isinstance(raw_sources, list):
                sources = [s for s in raw_sources if isinstance(s, dict)]
            raw_usage = llm_result.get("usage", {})
            if isinstance(raw_usage, dict):
                usage = raw_usage

        usage_out = _usage_payload(runtime, usage)
        runtime.sessions.append_turn(
            session_id,
            identity.scope_path,
            req.message,
            llm_answer,
            tool_trace=tool_trace,
            sources=sources,
            usage=usage_out,
        )
        _emit_chat_observability(runtime, 
            span,
            identity=identity,
            session_id=session_id,
            user_message=user_message,
            tool_trace=tool_trace,
            usage=usage,
        )

    if _looks_like_chart_request(user_message):
        return ChatResponse(
            answer_markdown=llm_answer,
            session_id=session_id,
            chart_spec=_sample_chart_spec(),
            chart_reason="PoC attaches a sample Vega-Lite chart when the message looks visualization-oriented.",
            mode="mcp-http+azure-tool-calling",
            tool_trace=tool_trace,
            sources=sources,
        )

    return ChatResponse(
        answer_markdown=llm_answer,
        session_id=session_id,
        chart_spec=None,
        chart_reason=None,
        mode="mcp-http+azure-tool-calling",
        tool_trace=tool_trace,
        sources=sources,
    )