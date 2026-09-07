"""Content-free spans and legacy-compatible completion log fields."""

import json
import logging
from contextlib import contextmanager

from opentelemetry import trace

from pascal.agent.budget import cost_usd

tracer = trace.get_tracer("diapason_agent")
log = logging.getLogger("diapason.chat")


@contextmanager
def operation(name: str):
    # Disabling exception events alone is insufficient: OTel also puts exception
    # text in Status.description unless set_status_on_exception is disabled.
    with tracer.start_as_current_span(
        name, record_exception=False, set_status_on_exception=False
    ) as span:
        try:
            yield span
        except BaseException as exc:
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise


def safe_arguments(value):
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if any(
                part in key.lower()
                for part in (
                    "token",
                    "secret",
                    "password",
                    "authorization",
                    "pdf_base64",
                    "api_key",
                )
            )
            else safe_arguments(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [safe_arguments(item) for item in value]
    return value


def completion(identity, session_id, outcome, config, duration_ms, prompt_version):
    storage = config.get("storage", {})
    blob = f"{identity.scope_path}/{session_id}.json"
    if storage.get("account_name"):
        blob = (
            f"https://{storage['account_name']}.blob.core.windows.net/"
            f"{storage.get('chat_container', 'chat-sessions')}/{blob}"
        )
    context = trace.get_current_span().get_span_context()
    fields = dict(
        customer=identity.customer_id,
        user=identity.user_id,
        instance=identity.instance,
        session=session_id,
        tokens_in=outcome.usage.get("input", 0),
        tokens_out=outcome.usage.get("output", 0),
        cached_tokens=outcome.usage.get("cached_input", 0),
        cost_usd=cost_usd(outcome.usage, config.get("azure_openai", {})),
        tools=",".join(dict.fromkeys(t["name"] for t in outcome.traces)),
        skills=(outcome.receipt or {}).get("skill", ""),
        blob=blob,
        status=outcome.status,
        persisted=outcome.persisted,
        duration_ms=duration_ms,
        rounds=outcome.rounds,
        ttft_ms=outcome.first_token_ms,
        prompt_version=prompt_version,
        trace_id=f"{context.trace_id:032x}",
        span_id=f"{context.span_id:016x}",
    )
    log.info(
        "chat done %s", " ".join(f"{key}={json.dumps(value)}" for key, value in fields.items())
    )
