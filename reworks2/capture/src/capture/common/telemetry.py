"""
OpenTelemetry bootstrap for diapason-agent.

Goals:
- Keep app logging API unchanged (still use logging.getLogger(...).info/exception).
- When OTEL_* log/traces exporters are configured, forward logs to Loki (OTLP logs)
  and traces to Tempo (OTLP traces).
- W3C Trace Context propagator so agent → MCP (and later Diapason) can share one trace.
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import Dict


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _parse_headers(raw: str) -> Dict[str, str]:
    """
    Parse OTEL_EXPORTER_OTLP_*HEADERS ("k1=v1,k2=v2").
    Values are URL-decoded (ops style: Bearer%20<token>).
    Values must not contain unescaped commas.
    """
    from urllib.parse import unquote

    out: Dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        if not k or not v:
            continue
        out[k.strip()] = unquote(v.strip())
    return out


def _headers_for(*, logs: bool) -> Dict[str, str]:
    """Prefer explicit *_HEADERS; else build from OTEL_EXPORTER_OTLP_TOKEN (+ org for logs)."""
    if logs:
        raw = _env("OTEL_EXPORTER_OTLP_LOGS_HEADERS") or _env("OTEL_EXPORTER_OTLP_HEADERS")
    else:
        raw = _env("OTEL_EXPORTER_OTLP_HEADERS")
    if raw:
        return _parse_headers(raw)

    token = _env("OTEL_EXPORTER_OTLP_TOKEN")
    if not token:
        return {}
    auth = f"Authorization=Bearer {token}"
    if not logs:
        return _parse_headers(auth)
    org = _env("OTEL_EXPORTER_OTLP_SCOPE_ORG_ID") or "mcc"
    return _parse_headers(f"{auth},X-Scope-OrgID={org}")


def _resource_from_env() -> object:
    # service.name + optional OTEL_RESOURCE_ATTRIBUTES (deployment.environment, …).
    from opentelemetry.sdk.resources import Resource

    attrs: Dict[str, str] = {}
    svc = _env("OTEL_SERVICE_NAME")
    if svc:
        attrs["service.name"] = svc
    extra = _env("OTEL_RESOURCE_ATTRIBUTES")
    if extra:
        for part in extra.split(","):
            part = part.strip()
            if not part:
                continue
            k, _, v = part.partition("=")
            if not k or not v:
                continue
            attrs[k.strip()] = v.strip()

    return Resource.create(attrs or None)


def _otel_enabled_for_logs() -> bool:
    return bool(
        _env("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
        or (_env("OTEL_EXPORTER_OTLP_ENDPOINT") and _env("OTEL_EXPORTER_OTLP_PROTOCOL"))
    )


def _otel_enabled_for_traces() -> bool:
    return bool(_env("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or _env("OTEL_EXPORTER_OTLP_ENDPOINT"))


def init_otel(*, logger_name: str = "diapason_agent") -> None:
    """
    Initialize OTel SDK if endpoints are configured.

    Safe to call even when opentelemetry packages are missing: no-op then.
    """
    if not (_otel_enabled_for_logs() or _otel_enabled_for_traces()):
        return

    try:
        from opentelemetry import trace
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        # Logs exporter is in a private module (underscore) in some OTel versions.
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.composite import CompositePropagator
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        try:
            from opentelemetry.sdk._logs import LoggingHandler  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            from opentelemetry.instrumentation.logging.handler import (  # type: ignore
                LoggingHandler,
            )
        try:
            from opentelemetry.baggage.propagation import W3CBaggagePropagator

            set_global_textmap(
                CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
            )
        except Exception:  # pragma: no cover
            set_global_textmap(TraceContextTextMapPropagator())
    except Exception as exc:
        logging.getLogger(logger_name).warning(
            "OpenTelemetry unavailable (%s) — continuing without OTel.", exc
        )
        return

    service_resource = _resource_from_env()
    log = logging.getLogger(logger_name)
    svc = _env("OTEL_SERVICE_NAME") or "(unnamed)"

    # Traces — pass full signal URL (exporter does not append /v1/traces when set).
    if _otel_enabled_for_traces():
        traces_endpoint = _env("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or _env(
            "OTEL_EXPORTER_OTLP_ENDPOINT"
        )
        trace_headers = _headers_for(logs=False)
        trace_exporter = OTLPSpanExporter(
            endpoint=traces_endpoint or None,
            headers=trace_headers or None,
        )
        tracer_provider = TracerProvider(resource=service_resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
        trace.set_tracer_provider(tracer_provider)
        log.info("OpenTelemetry traces service=%s → %s", svc, traces_endpoint)

    logger_provider = None

    # Logs — pass full signal URL (e.g. .../otlp/v1/logs); exporter POSTs as-is.
    if _otel_enabled_for_logs():
        logs_endpoint = _env("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") or _env(
            "OTEL_EXPORTER_OTLP_ENDPOINT"
        )
        logs_headers = _headers_for(logs=True)

        logger_provider = LoggerProvider(resource=service_resource)
        log_exporter = OTLPLogExporter(
            endpoint=logs_endpoint or None,
            headers=logs_headers or None,
        )
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        set_logger_provider(logger_provider)

        handler = LoggingHandler(logger_provider=logger_provider)
        logging.getLogger().addHandler(handler)
        log.info("OpenTelemetry logs service=%s → %s", svc, logs_endpoint)

    def _shutdown() -> None:
        try:
            if _otel_enabled_for_logs():
                if logger_provider is not None:
                    logger_provider.shutdown()
        except Exception:
            pass
        try:
            trace.get_tracer_provider().shutdown()
        except Exception:
            pass

    atexit.register(_shutdown)


def get_tracer(name: str = "diapason_agent"):
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except Exception:
        return None


# --- chat / cost helpers (safe without OTel packages) ---

QUERY_PREVIEW_MAX = 120

# Placeholder rates when CHAT_CONFIG omits them (ops should set real values).
_DEFAULT_INPUT_USD_PER_1M = 0.0
_DEFAULT_OUTPUT_USD_PER_1M = 0.0


def query_preview(text: str, max_chars: int = QUERY_PREVIEW_MAX) -> str:
    s = " ".join((text or "").split())
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"


def session_blob_path(scope: str, session_id: str) -> str:
    return f"{scope}/{session_id}.json"


def session_blob_url(config: dict, scope: str, session_id: str) -> str:
    storage = config.get("storage") if isinstance(config.get("storage"), dict) else {}
    account = str(storage.get("account_name", "") or "").strip()
    container = str(storage.get("chat_container", "") or "").strip() or "chat-sessions"
    path = session_blob_path(scope, session_id)
    if not account:
        return path
    return f"https://{account}.blob.core.windows.net/{container}/{path}"


def usage_from_completion(response: object) -> dict:
    """Normalize Azure/OpenAI usage object → {input, output, total} ints."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return {}
    if isinstance(usage, dict):
        inp = usage.get("prompt_tokens", usage.get("input_tokens"))
        out = usage.get("completion_tokens", usage.get("output_tokens"))
        total = usage.get("total_tokens")
    else:
        inp = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
        out = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None)
        total = getattr(usage, "total_tokens", None)
    result: dict = {}
    if isinstance(inp, (int, float)):
        result["input"] = int(inp)
    if isinstance(out, (int, float)):
        result["output"] = int(out)
    if isinstance(total, (int, float)):
        result["total"] = int(total)
    elif "input" in result or "output" in result:
        result["total"] = int(result.get("input", 0)) + int(result.get("output", 0))
    return result


def merge_usage(a: dict, b: dict) -> dict:
    if not a:
        return dict(b) if b else {}
    if not b:
        return dict(a)
    out = {
        "input": int(a.get("input", 0)) + int(b.get("input", 0)),
        "output": int(a.get("output", 0)) + int(b.get("output", 0)),
        "total": int(a.get("total", 0)) + int(b.get("total", 0)),
    }
    return out


def estimate_cost_usd(usage: dict, azure_openai_config: dict | None) -> float | None:
    """Estimate USD from usage + CHAT_CONFIG.azure_openai rates. None if no tokens."""
    if not usage:
        return None
    inp = int(usage.get("input", 0) or 0)
    out = int(usage.get("output", 0) or 0)
    if inp == 0 and out == 0:
        return None
    ao = azure_openai_config if isinstance(azure_openai_config, dict) else {}
    try:
        in_rate = float(ao.get("input_usd_per_1m", _DEFAULT_INPUT_USD_PER_1M))
    except (TypeError, ValueError):
        in_rate = _DEFAULT_INPUT_USD_PER_1M
    try:
        out_rate = float(ao.get("output_usd_per_1m", _DEFAULT_OUTPUT_USD_PER_1M))
    except (TypeError, ValueError):
        out_rate = _DEFAULT_OUTPUT_USD_PER_1M
    return (inp * in_rate + out * out_rate) / 1_000_000.0


def tools_csv(tool_trace: list | None) -> str:
    if not tool_trace:
        return ""
    names: list[str] = []
    seen: set[str] = set()
    for item in tool_trace:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("tool") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return ",".join(names)


def skills_csv(skill_run: dict | None, tool_trace: list | None = None) -> str:
    names: list[str] = []
    seen: set[str] = set()
    if isinstance(skill_run, dict):
        skill = str(skill_run.get("skill") or "").strip()
        if skill:
            seen.add(skill)
            names.append(skill)
    if tool_trace:
        for item in tool_trace:
            if not isinstance(item, dict):
                continue
            skill = str(item.get("skill") or "").strip()
            if skill and skill not in seen:
                seen.add(skill)
                names.append(skill)
    return ",".join(names)
