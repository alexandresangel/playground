import json
import logging
from pathlib import Path

import httpx
from conftest import FakeMcp, FakeModel, MemoryStore
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from pascal.adapters.mcp import HttpMcpTransport
from pascal.main import create_app
from pascal.observability import events
from pascal.observability.bootstrap import _headers, _resource, instrument_app
from pascal.tools.context import McpServerContext


def test_existing_exporter_headers_and_resource(monkeypatch):
    for key in (
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
        "OTEL_EXPORTER_OTLP_SCOPE_ORG_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TOKEN", "test-only-token")
    assert _headers("logs") == {"Authorization": "Bearer test-only-token", "X-Scope-OrgID": "mcc"}
    assert _headers("traces") == {"Authorization": "Bearer test-only-token"}
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS", "Authorization=Bearer%20specific,X-Scope-OrgID=tenant"
    )
    assert _headers("logs")["Authorization"] == "Bearer specific"
    monkeypatch.setenv("OTEL_SERVICE_NAME", "diapason-agent-dev")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment=dev")
    assert _resource().attributes["service.name"] == "diapason-agent-dev"


async def test_model_error_has_no_secret_in_trace_or_log(
    service_factory, identity, monkeypatch, caplog
):
    provider, exporter = TracerProvider(), InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(events, "tracer", provider.get_tracer("test"))
    caplog.set_level(logging.INFO, logger="diapason.chat")
    service = service_factory(model=FakeModel([RuntimeError("SECRET_REMOTE_RESPONSE")]))
    handle = await service.open(identity=identity, message="PRIVATE USER QUESTION")
    await handle.task
    spans = exporter.get_finished_spans()
    assert {span.name for span in spans} == {"chat.model", "chat.completion"}
    rendered = json.dumps(
        [
            {
                "attributes": dict(s.attributes),
                "status": s.status.description,
                "events": [str(e) for e in s.events],
            }
            for s in spans
        ]
    )
    for secret in ("SECRET_REMOTE_RESPONSE", "PRIVATE USER QUESTION"):
        assert secret not in rendered
        assert secret not in caplog.text
    model = next(span for span in spans if span.name == "chat.model")
    completion = next(span for span in spans if span.name == "chat.completion")
    assert model.parent.span_id == completion.context.span_id
    assert f"{completion.context.trace_id:032x}" in caplog.text
    assert "persisted=true" in caplog.text
    provider.shutdown()


def test_ingress_trace_parent_and_ambient_header_capture_are_safe(
    config, auth, headers, monkeypatch
):
    provider, exporter = TracerProvider(), InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(events, "tracer", provider.get_tracer("test"))
    monkeypatch.setenv("OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST", ".*")
    monkeypatch.setattr(
        "pascal.main.instrument_app", lambda app: instrument_app(app, tracer_provider=provider)
    )
    app = create_app(
        config=config,
        auth=auth,
        model=FakeModel(),
        transport=FakeMcp(),
        store=MemoryStore(),
        prompt_text="Pascal",
        root=Path.cwd(),
    )
    trace_id = "a" * 32
    with TestClient(app) as client:
        result = client.post(
            "/api/chat",
            headers=headers
            | {
                "traceparent": f"00-{trace_id}-bbbbbbbbbbbbbbbb-01",
            },
            json={"message": "PRIVATE QUESTION"},
        )
        assert result.status_code == 200
    spans = exporter.get_finished_spans()
    completion = next(s for s in spans if s.name == "chat.completion")
    assert f"{completion.context.trace_id:032x}" == trace_id
    server = next(s for s in spans if s.context.span_id == completion.parent.span_id)
    assert server.parent.span_id == int("bbbbbbbbbbbbbbbb", 16)
    rendered = str([(s.attributes, s.events, s.status.description) for s in spans])
    assert "API-TOKEN" not in rendered
    assert headers["Authorization"] not in rendered
    assert "PRIVATE QUESTION" not in rendered
    provider.shutdown()


async def test_w3c_context_reaches_mcp_without_credentials_in_span(monkeypatch):
    provider, exporter = TracerProvider(), InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(events, "tracer", provider.get_tracer("test"))
    received = []

    async def responder(request):
        received.append(request.headers)
        rpc = json.loads(request.content)
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": rpc["id"], "result": {"tools": []}}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    adapter = HttpMcpTransport({}, 4096, client)
    with events.operation("chat.tool") as span:
        await adapter.request(
            McpServerContext("default", "D", "https://mcp/mcp", {"Authorization": "Bearer secret"}),
            "tools/list",
            {},
        )
        assert f"{span.get_span_context().trace_id:032x}" in received[0]["traceparent"]
    assert "secret" not in str(exporter.get_finished_spans()[0].attributes)
    await adapter.close()
    provider.shutdown()
