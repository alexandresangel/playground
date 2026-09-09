"""OTLP logs, traces and optional metrics with the Diapason deployment contract.

Applications own operation names; this module owns exporters and safe primitives.
There is no model/prompt auto-instrumentation and no content or identity metric label.
"""

import atexit
import logging
import os
import time
from contextlib import contextmanager
from typing import Any
from urllib.parse import unquote

from opentelemetry import metrics, trace

_initialized = False
_providers: list[Any] = []
_tracer = trace.get_tracer("diapason.integrations")
_meter = metrics.get_meter("diapason.integrations")
_operations = _meter.create_counter("diapason.operation.count", unit="{operation}")
_duration = _meter.create_histogram("diapason.operation.duration", unit="s")
_turns = _meter.create_counter("diapason.turn.count", unit="{turn}")
_first_token = _meter.create_histogram("diapason.chat.time_to_first_token", unit="s")
_tokens = _meter.create_counter("diapason.model.token.usage", unit="{token}")


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _parse_headers(raw: str) -> dict[str, str]:
    headers = {}
    for part in raw.split(","):
        key, separator, value = part.strip().partition("=")
        if separator and key and value:
            headers[key.strip()] = unquote(value.strip())
    return headers


def _headers(signal: str) -> dict[str, str]:
    specific = _env(f"OTEL_EXPORTER_OTLP_{signal.upper()}_HEADERS")
    generic = _env("OTEL_EXPORTER_OTLP_HEADERS")
    if specific or generic:
        return _parse_headers(specific or generic)
    token = _env("OTEL_EXPORTER_OTLP_TOKEN")
    if not token:
        return {}
    result = {"Authorization": f"Bearer {token}"}
    tenant = _env("OTEL_EXPORTER_OTLP_SCOPE_ORG_ID")
    if signal == "logs":
        result["X-Scope-OrgID"] = tenant or "mcc"
    elif tenant:
        result["X-Scope-OrgID"] = tenant
    return result


def signal_endpoint(signal: str) -> str:
    explicit = _env(f"OTEL_EXPORTER_OTLP_{signal.upper()}_ENDPOINT")
    if explicit:
        return explicit
    # Enabling metrics requires a metrics receiver, never an inferred Loki/Tempo URL.
    if signal == "metrics":
        return ""
    generic = _env("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not generic:
        return ""
    mode = _env("DIAPASON_OTLP_ENDPOINT_MODE") or "legacy_full_signal"
    if mode == "standard":
        return generic.rstrip("/") + "/v1/" + signal
    if mode != "legacy_full_signal":
        raise ValueError("DIAPASON_OTLP_ENDPOINT_MODE must be standard or legacy_full_signal")
    if signal == "logs" and not _env("OTEL_EXPORTER_OTLP_PROTOCOL"):
        return ""
    return generic


def _resource(service_name: str = "diapason_agent"):
    from opentelemetry.sdk.resources import Resource

    attributes = {"service.name": _env("OTEL_SERVICE_NAME") or service_name}
    attributes.update(_parse_headers(_env("OTEL_RESOURCE_ATTRIBUTES")))
    return Resource.create(attributes)


class ApplicationLogsOnly(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # SDK exceptions may contain request URLs, headers or model content. Only
        # the application's explicitly content-free operational events are exported.
        return record.name.startswith(("capture.", "diapason.", "pascal."))


def init_otel(service_name: str = "diapason_agent") -> None:
    global _initialized
    if _initialized:
        return
    endpoints = {signal: signal_endpoint(signal) for signal in ("traces", "logs", "metrics")}
    if not any(endpoints.values()):
        return
    for signal, endpoint in endpoints.items():
        protocol = _env(f"OTEL_EXPORTER_OTLP_{signal.upper()}_PROTOCOL") or _env(
            "OTEL_EXPORTER_OTLP_PROTOCOL"
        )
        if endpoint and protocol and protocol != "http/protobuf":
            raise ValueError("These exporters require OTLP http/protobuf")

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.logging.handler import LoggingHandler
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = _resource(service_name)
    if endpoints["traces"]:
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoints["traces"], headers=_headers("traces") or None)
            )
        )
        trace.set_tracer_provider(provider)
        _providers.append(provider)
    if endpoints["logs"]:
        provider = LoggerProvider(resource=resource)
        provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=endpoints["logs"], headers=_headers("logs") or None)
            )
        )
        set_logger_provider(provider)
        handler = LoggingHandler(logger_provider=provider)
        handler.addFilter(ApplicationLogsOnly())
        logging.getLogger().addHandler(handler)
        _providers.append(provider)
    if endpoints["metrics"]:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoints["metrics"], headers=_headers("metrics") or None)
        )
        provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(provider)
        _providers.append(provider)
    _initialized = True
    atexit.register(shutdown_otel)


def flush_otel() -> None:
    for provider in _providers:
        provider.force_flush(timeout_millis=5000)


def shutdown_otel() -> None:
    while _providers:
        _providers.pop().shutdown()


def instrument_app(app: Any, *, tracer_provider=None, meter_provider=None) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        http_capture_headers_server_request=[],
        http_capture_headers_server_response=[],
        http_capture_headers_sanitize_fields=[".*"],
        exclude_spans=["receive", "send"],
    )


@contextmanager
def operation(name: str, *, attributes: dict | None = None):
    started, status = time.monotonic(), "success"
    with _tracer.start_as_current_span(
        name,
        attributes=attributes,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        observed = OperationSpan(span)
        try:
            yield observed
        except BaseException as exc:
            status = "cancelled" if type(exc).__name__ == "CancelledError" else "error"
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
        finally:
            span_status = observed.status
            if (
                status == "success"
                and span_status
                and span_status.status_code == trace.StatusCode.ERROR
            ):
                status = "error"
            labels = {"operation": name, "status": status}
            _operations.add(1, labels)
            _duration.record(time.monotonic() - started, labels)


class OperationSpan:
    """Observe business status even when tracing is disabled or this span is unsampled."""

    def __init__(self, span):
        self.span = span
        self.status = None

    def set_status(self, status, description=None):
        self.status = status if isinstance(status, trace.Status) else trace.Status(status)
        self.span.set_status(status, description)

    def __getattr__(self, name):
        return getattr(self.span, name)


def record_turn(status: str, *, first_token_ms: int | None = None) -> None:
    allowed = {"completed", "cancelled", "timeout", "limit_reached", "failed", "persistence_failed"}
    _turns.add(1, {"status": status if status in allowed else "other"})
    if first_token_ms is not None:
        _first_token.record(max(0, first_token_ms) / 1000)


def record_model_usage(usage: dict) -> None:
    for direction in ("input", "output"):
        count = usage.get(direction, 0)
        if isinstance(count, int) and count > 0:
            _tokens.add(count, {"direction": direction, "estimated": bool(usage.get("estimated"))})
