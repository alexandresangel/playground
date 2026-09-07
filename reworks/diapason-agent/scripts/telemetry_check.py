"""Isolated-process test of the real OTLP HTTP exporters against a local collector."""

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from pascal.observability.bootstrap import flush_otel, init_otel
from pascal.observability.events import operation

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
    flush_otel()
    traces = [record for record in received if record[0] == "/v1/traces"]
    logs = [record for record in received if record[0] == "/otlp/v1/logs"]
    assert traces and logs
    for _, headers, _ in received:
        assert headers["Authorization"] == "Bearer fixture-token"
        assert headers["X-Scope-OrgID"] == "mcc"
    trace_data = ExportTraceServiceRequest.FromString(traces[0][2])
    log_data = ExportLogsServiceRequest.FromString(logs[0][2])
    span = trace_data.resource_spans[0].scope_spans[0].spans[0]
    record = log_data.resource_logs[0].scope_logs[0].log_records[0]
    assert span.name == "chat.model"
    assert record.trace_id == span.trace_id
    assert record.body.string_value == "safe operational event"
    print("Real OTLP trace/log exporters: endpoints, Bearer/tenant headers and correlation passed.")
finally:
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()
