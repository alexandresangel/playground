"""Capture correlation on the existing company provider; never log document content."""

from typing import Any, Optional
import logging

from telemetry import session_blob_path, session_blob_url
from capture.runtime import Runtime


def set_span_attr(span: Any, key: str, value: Any) -> None:
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


def apply_identity_span_attrs(runtime: Runtime, 
    span: Any,
    *,
    customer_id: Any = None,
    user_id: Any = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> None:
    if span is None:
        return
    set_span_attr(span, "diapason.customer_id", customer_id)
    set_span_attr(span, "enduser.id", user_id)
    set_span_attr(span, "diapason.user_id", user_id)
    if session_id and scope:
        set_span_attr(span, "diapason.session_id", session_id)
        set_span_attr(span, "diapason.scope", scope)
        path = session_blob_path(scope, session_id)
        set_span_attr(span, "diapason.session_blob_path", path)
        set_span_attr(
            span, "diapason.session_blob_url", session_blob_url(runtime.config, scope, session_id)
        )
    elif session_id:
        set_span_attr(span, "diapason.session_id", session_id)
    elif scope:
        set_span_attr(span, "diapason.scope", scope)


def record_capture_result(runtime: Runtime, span, *, identity, session_id: str, result: dict) -> None:
    apply_identity_span_attrs(runtime, span, customer_id=identity.customer_id, user_id=identity.user_id,
                               session_id=session_id, scope=identity.scope_path)
    set_span_attr(span, "ai.result_success", bool(result.get("success")))
    logging.getLogger("diapason.chat").info("Capture completed success=%s", bool(result.get("success")))