"""observability: relocated Pascal behavior with explicit runtime dependencies."""

from __future__ import annotations
from dia_jwt.fastapi import Identity
from pascal.runtime import Runtime
from telemetry import estimate_cost_usd, session_blob_path, session_blob_url, skills_csv as legacy_workflow_names, tools_csv
from typing import Any, Dict, List, Optional
import logging

log = logging.getLogger("diapason.chat")


def _aoai_rates(runtime: Runtime) -> dict:
    ao = runtime.config.get("azure_openai") if isinstance(runtime.config.get("azure_openai"), dict) else {}
    return ao


def _usage_payload(runtime: Runtime, usage: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not usage:
        return None
    out = dict(usage)
    cost = estimate_cost_usd(usage, _aoai_rates(runtime))
    if cost is not None:
        out["cost_usd"] = cost
    return out


def _set_span_attr(span: Any, key: str, value: Any) -> None:
    if span is None or value is None:
        return
    # Identity IDs as strings so Tempo TraceQL =~ filters work.
    if key in ("diapason.customer_id", "diapason.user_id", "enduser.id"):
        text = str(value).strip()
        if text:
            span.set_attribute(key, text)
        return
    if isinstance(value, bool):
        span.set_attribute(key, value)
    elif isinstance(value, (int, float)):
        span.set_attribute(key, value)
    else:
        text = str(value).strip()
        if text:
            span.set_attribute(key, text)


def _logfmt_value(value: Any) -> str:
    """Quote values that would break Loki field parsers."""
    s = "" if value is None else str(value)
    if s == "" or any(c in s for c in ' \t\n="\\'):
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return s


def _apply_identity_span_attrs(runtime: Runtime, 
    span: Any,
    *,
    customer_id: Any = None,
    user_id: Any = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> None:
    if span is None:
        return
    _set_span_attr(span, "diapason.customer_id", customer_id)
    _set_span_attr(span, "enduser.id", user_id)
    _set_span_attr(span, "diapason.user_id", user_id)
    if session_id and scope:
        _set_span_attr(span, "diapason.session_id", session_id)
        _set_span_attr(span, "diapason.scope", scope)
        path = session_blob_path(scope, session_id)
        _set_span_attr(span, "diapason.session_blob_path", path)
        _set_span_attr(
            span, "diapason.session_blob_url", session_blob_url(runtime.config, scope, session_id)
        )
    elif session_id:
        _set_span_attr(span, "diapason.session_id", session_id)
    elif scope:
        _set_span_attr(span, "diapason.scope", scope)


def _emit_chat_observability(runtime: Runtime, 
    span: Any,
    *,
    identity: Identity,
    session_id: str,
    user_message: str,
    tool_trace: Optional[List[Dict[str, Any]]] = None,
    skill_run: Optional[Dict[str, Any]] = None,
    usage: Optional[Dict[str, Any]] = None,
) -> None:
    preview = "[redacted]"
    tools = tools_csv(tool_trace)
    workflow_names = legacy_workflow_names(skill_run, tool_trace)
    usage_out = _usage_payload(runtime, usage or {})
    blob = session_blob_url(runtime.config, identity.scope_path, session_id)
    _apply_identity_span_attrs(runtime, 
        span,
        customer_id=identity.customer_id,
        user_id=identity.user_id,
        session_id=session_id,
        scope=identity.scope_path,
    )
    _set_span_attr(span, "diapason.chat.query_preview", preview)
    _set_span_attr(span, "diapason.chat.tools", tools or "-")
    _set_span_attr(span, "diapason.chat.skills", workflow_names or "-")
    tokens_in = int(usage_out.get("input", 0)) if usage_out else 0
    tokens_out = int(usage_out.get("output", 0)) if usage_out else 0
    if usage_out and "cost_usd" in usage_out:
        cost = float(usage_out["cost_usd"])
    else:
        cost = 0.0
    if usage_out:
        if "input" in usage_out:
            _set_span_attr(span, "gen_ai.usage.input_tokens", usage_out["input"])
        if "output" in usage_out:
            _set_span_attr(span, "gen_ai.usage.output_tokens", usage_out["output"])
        if "total" in usage_out:
            _set_span_attr(span, "gen_ai.usage.total_tokens", usage_out["total"])
        if "cost_usd" in usage_out:
            _set_span_attr(span, "diapason.chat.cost_usd", float(usage_out["cost_usd"]))
    # Always emit numeric cost_usd (0 when unknown) so Loki unwrap works.
    # preview last so tools/skills stay simple tokens for the dashboard regexp.
    log.info(
        "chat done customer=%s user=%s session=%s tokens_in=%s tokens_out=%s cost_usd=%s "
        "tools=%s skills=%s blob=%s preview=%s",
        identity.customer_id,
        identity.user_id,
        session_id,
        tokens_in,
        tokens_out,
        cost,
        _logfmt_value(tools),
        _logfmt_value(workflow_names),
        blob,
        _logfmt_value(preview),
    )
