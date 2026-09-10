"""Existing JSON and server-sent event chat endpoints."""

from __future__ import annotations
from contextlib import nullcontext
from dia_jwt.fastapi import Identity
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pascal.agent.context import _prepare_chat_context
from pascal.agent.service import _build_response, _iter_chat_stream_events
from pascal.api.schemas import ChatRequest, ChatResponse
from pascal.observability.http import _emit_chat_observability, _usage_payload
from pascal.runtime import Runtime, locale_from_request
from source_extract import merge_source_lists
from typing import Any, Dict, Iterator, List
import json

CHAT_SESSION_HEADER = "X-Diapason-Chat-Session"


def _sse_line(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()
    get_identity = runtime.get_identity

    @router.post("/api/chat", response_model=ChatResponse)
    def chat(
        req: ChatRequest,
        request: Request,
        identity: Identity = Depends(get_identity),
    ) -> ChatResponse:
        return _build_response(runtime, req, identity, locale=locale_from_request(request))

    @router.post("/api/chat/stream")
    def chat_stream(
        req: ChatRequest,
        request: Request,
        identity: Identity = Depends(get_identity),
    ) -> StreamingResponse:
        loc = locale_from_request(request)
        session_id, messages, mcp_summary, route_names, _route_token, user_message = _prepare_chat_context(runtime, 
            req, identity, locale=loc
        )

        def generate() -> Iterator[str]:
            answer_parts: List[str] = []
            tool_trace: List[Dict[str, Any]] = []
            sources: List[Dict[str, str]] = []
            usage: Dict[str, Any] = {}
            span_cm = (
                runtime.tracer.start_as_current_span("chat.completion", record_exception=False, set_status_on_exception=False)
                if runtime.tracer
                else nullcontext()
            )
            with span_cm as span:
                for event in _iter_chat_stream_events(runtime, 
                    messages,
                    user_message,
                    session_id,
                    mcp_summary,
                    identity.mcp,
                    req.client_timezone,
                    route_names,
                    locale=loc,
                ):
                    if event.get("type") == "delta" and event.get("content"):
                        answer_parts.append(str(event["content"]))
                    elif event.get("type") == "done":
                        raw_trace = event.get("tool_trace", [])
                        if isinstance(raw_trace, list):
                            tool_trace = [t for t in raw_trace if isinstance(t, dict)]
                        raw_sources = event.get("sources", [])
                        if isinstance(raw_sources, list):
                            sources = [s for s in raw_sources if isinstance(s, dict)]
                        raw_usage = event.get("usage", {})
                        if isinstance(raw_usage, dict):
                            usage = raw_usage
                    elif event.get("type") == "sources":
                        raw_items = event.get("items", [])
                        if isinstance(raw_items, list):
                            batch = [s for s in raw_items if isinstance(s, dict)]
                            sources = merge_source_lists(sources, batch, locale=loc)
                    yield _sse_line(event)
                usage_out = _usage_payload(runtime, usage)
                runtime.sessions.append_turn(
                    session_id,
                    identity.scope_path,
                    req.message,
                    "".join(answer_parts),
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
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                CHAT_SESSION_HEADER: session_id,
            },
        )

    return router
