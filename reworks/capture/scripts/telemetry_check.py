"""Isolated-process test of the real OTLP HTTP exporters against a local collector."""

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from capture.observability.telemetry import (
    flush_otel,
    init_otel,
    operation,
    record_model_usage,
    record_turn,
    shutdown_otel,
)

received = []


class Collector(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        received.append((self.path, dict(self.headers), body))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Collector)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f"http://127.0.0.1:{server.server_port}"
os.environ.update(
    {
        "OTEL_SERVICE_NAME": "diapason-agent-test",
        "OTEL_RESOURCE_ATTRIBUTES": "deployment.environment=dev",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": base + "/v1/traces",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": base + "/otlp/v1/logs",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": base + "/v1/metrics",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_METRICS_HEADERS": "",
        "OTEL_EXPORTER_OTLP_HEADERS": "",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS": "",
        "OTEL_EXPORTER_OTLP_TOKEN": "fixture-token",
        "OTEL_EXPORTER_OTLP_SCOPE_ORG_ID": "mcc",
        "OTEL_TRACES_SAMPLER": "always_on",
    }
)
logging.basicConfig(level=logging.INFO)
try:
    init_otel()
    with operation("chat.model"):
        logging.getLogger("diapason.chat").info("safe operational event")
        record_model_usage({"input": 20, "output": 5})
    record_turn("completed", first_token_ms=100)
    try:
        with operation("capture.run"):
            raise RuntimeError("PRIVATE EXCEPTION BODY")
    except RuntimeError:
        pass
    flush_otel()
    traces = [record for record in received if record[0] == "/v1/traces"]
    logs = [record for record in received if record[0] == "/otlp/v1/logs"]
    metric_batches = [record for record in received if record[0] == "/v1/metrics"]
    assert traces and logs and metric_batches
    for _, headers, _ in received:
        assert headers["Authorization"] == "Bearer fixture-token"
        assert headers["X-Scope-OrgID"] == "mcc"
    trace_data = ExportTraceServiceRequest.FromString(traces[0][2])
    log_data = ExportLogsServiceRequest.FromString(logs[0][2])
    spans = [
        span
        for resource in trace_data.resource_spans
        for scope in resource.scope_spans
        for span in scope.spans
    ]
    span = next(span for span in spans if span.name == "chat.model")
    record = log_data.resource_logs[0].scope_logs[0].log_records[0]
    assert span.name == "chat.model"
    assert record.trace_id == span.trace_id
    assert record.body.string_value == "safe operational event"
    metric_data = ExportMetricsServiceRequest.FromString(metric_batches[0][2])
    exported = {
        metric.name: metric
        for resource in metric_data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }
    assert {
        "diapason.operation.count",
        "diapason.operation.duration",
        "diapason.turn.count",
        "diapason.chat.time_to_first_token",
        "diapason.model.token.usage",
    } <= set(exported)
    tokens = exported["diapason.model.token.usage"].sum.data_points
    assert sum(point.as_int for point in tokens) == 25
    operation_points = exported["diapason.operation.count"].sum.data_points
    assert any(
        any(a.key == "status" and a.value.string_value == "error" for a in point.attributes)
        for point in operation_points
    )
    for _, _, body in received:
        assert b"PRIVATE EXCEPTION BODY" not in body
        assert b"fixture-token" not in body
    labels = [
        a.key
        for metric in exported.values()
        for kind in ("sum", "histogram")
        for point in getattr(metric, kind).data_points
        for a in point.attributes
    ]
    assert not {"customer", "user", "session", "trade_type", "prompt", "tool", "pdf"} & set(labels)
    print(
        "Real OTLP logs/traces/metrics: endpoints, auth/tenant headers, "
        "labels, privacy and correlation passed."
    )
finally:
    shutdown_otel()
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()
