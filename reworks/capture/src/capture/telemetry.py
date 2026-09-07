"""OpenTelemetry logs and traces, compatible with the existing Loki/Tempo settings."""

from __future__ import annotations

import atexit
import logging
import os
from typing import Any
from urllib.parse import unquote

_initialized = False


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _parse_headers(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in raw.split(","):
        key, separator, value = part.strip().partition("=")
        if separator and key and value:
            result[key.strip()] = unquote(value.strip())
    return result


def _headers(signal: str) -> dict[str, str]:
    specific = _env(f"OTEL_EXPORTER_OTLP_{signal.upper()}_HEADERS")
    generic = _env("OTEL_EXPORTER_OTLP_HEADERS")
    if specific or generic:
        return _parse_headers(specific or generic)
    token = _env("OTEL_EXPORTER_OTLP_TOKEN")
    if not token:
        return {}
    headers = {"Authorization": f"Bearer {token}"}
    scope = _env("OTEL_EXPORTER_OTLP_SCOPE_ORG_ID")
    if signal == "logs":
        headers["X-Scope-OrgID"] = scope or "mcc"
    elif scope:
        headers["X-Scope-OrgID"] = scope
    return headers


def _resource() -> Any:
    from opentelemetry.sdk.resources import Resource

    attributes: dict[str, str] = {
        "service.name": _env("OTEL_SERVICE_NAME") or "capture",
    }
    for part in _env("OTEL_RESOURCE_ATTRIBUTES").split(","):
        key, separator, value = part.strip().partition("=")
        if separator and key and value:
            attributes[key.strip()] = value.strip()
    return Resource.create(attributes)


def init_otel() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True
    traces_endpoint = _env("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or _env(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    logs_endpoint = _env("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") or (
        _env("OTEL_EXPORTER_OTLP_ENDPOINT") if _env("OTEL_EXPORTER_OTLP_PROTOCOL") else ""
    )
    if not traces_endpoint and not logs_endpoint:
        return

    try:
        from opentelemetry import trace
        from opentelemetry._logs import set_logger_provider

        try:
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        except ImportError:  # pragma: no cover - exporter module moved between releases
            from opentelemetry.exporter.otlp.proto.http.log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.composite import CompositePropagator
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        try:
            from opentelemetry.baggage.propagation import W3CBaggagePropagator

            set_global_textmap(
                CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
            )
        except ImportError:  # pragma: no cover
            set_global_textmap(TraceContextTextMapPropagator())
    except ImportError as exc:  # pragma: no cover
        logging.getLogger("capture").warning("OpenTelemetry unavailable: %s", exc)
        return

    resource = _resource()
    tracer_provider = None
    logger_provider = None
    if traces_endpoint:
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=traces_endpoint, headers=_headers("traces") or None)
            )
        )
        trace.set_tracer_provider(tracer_provider)
    if logs_endpoint:
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=logs_endpoint, headers=_headers("logs") or None)
            )
        )
        set_logger_provider(logger_provider)
        logging.getLogger().addHandler(LoggingHandler(logger_provider=logger_provider))

    def shutdown() -> None:
        if logger_provider is not None:
            logger_provider.shutdown()
        if tracer_provider is not None:
            tracer_provider.shutdown()

    atexit.register(shutdown)


def instrument_app(app: Any) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover - instrumentation is best effort
        logging.getLogger("capture").warning("OpenTelemetry instrumentation unavailable: %s", exc)
