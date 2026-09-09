"""Content-free spans and legacy-compatible completion log fields."""

import json
import logging

from opentelemetry import trace

from pascal.agent.budget import cost_usd
from pascal.compatibility import completion_prefix
from pascal.observability.telemetry import record_turn

log = logging.getLogger("diapason.chat")


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
    record_turn(outcome.status, first_token_ms=outcome.first_token_ms)
    fields = completion_prefix(
        identity,
        session_id,
        outcome.usage,
        cost_usd(outcome.usage, config.get("azure_openai", {})),
        ",".join(dict.fromkeys(t["name"] for t in outcome.traces)),
        (outcome.receipt or {}).get("operation", ""),
    )
    fields.update(
        instance=identity.instance,
        cached_tokens=outcome.usage.get("cached_input", 0),
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
