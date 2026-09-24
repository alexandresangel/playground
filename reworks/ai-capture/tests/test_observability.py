import logging
import pytest
from fastapi import APIRouter, HTTPException
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from langsmith import get_tracing_context

from capture.observability import ai
from capture.observability.http import apply_identity_span_attrs


def exporter():
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    return memory, provider


def test_ai_spans_record_usage_and_redact_exception(monkeypatch):
    memory, provider = exporter()
    monkeypatch.setattr(ai, "get_tracer", lambda name: provider.get_tracer(name))
    with pytest.raises(ValueError):
        with ai.ai_span("ai.test.model") as span:
            ai.record_usage(span, {"input": 5, "output": 2, "total": 7})
            raise ValueError("private PDF and prompt")
    result = memory.get_finished_spans()[0]
    assert result.attributes["gen_ai.usage.total_tokens"] == 7
    assert result.attributes["ai.outcome"] == "error" and result.attributes["ai.duration_ms"] >= 0
    assert result.events == () and result.status.description is None
    assert "private" not in str(result.attributes)
    provider.shutdown()


def test_graph_tracing_disabled_per_context(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    with ai.private_graph_run():
        assert get_tracing_context()["enabled"] is False


def test_new_prefixed_endpoint_errors_are_redacted(service, caplog):
    router = APIRouter()
    @router.get("/new-workflow")
    def future_workflow():
        raise HTTPException(400, "private document content")
    service.app.include_router(router, prefix="/api/v2")
    caplog.set_level(logging.WARNING, logger="capture")
    response = service.client.get("/api/v2/new-workflow")
    assert response.status_code == 400
    assert response.json()["detail"] == "private document content"
    assert "private document content" not in caplog.text


def test_incoming_trace_is_parent_of_http_span(service):
    memory, provider = exporter()
    service.runtime.tracer = provider.get_tracer("http")
    trace_id = "0123456789abcdef0123456789abcdef"
    parent_id = "0123456789abcdef"
    response = service.client.get("/api/health", headers={"traceparent": f"00-{trace_id}-{parent_id}-01"})
    assert response.status_code == 200
    result = memory.get_finished_spans()[0]
    assert result.context.trace_id == int(trace_id, 16)
    assert result.parent.span_id == int(parent_id, 16)
    provider.shutdown()


def test_correlation_spans_have_no_storage_links(service):
    memory, provider = exporter()
    with provider.get_tracer("http").start_as_current_span("capture.completion") as span:
        apply_identity_span_attrs(service.runtime, span, customer_id=7, user_id=42,
                                  session_id="pascal-session", scope=service.scope)
    attrs = dict(memory.get_finished_spans()[0].attributes)
    assert attrs == {
        "diapason.customer_id": "7", "enduser.id": "42", "diapason.user_id": "42",
        "diapason.session_id": "pascal-session", "diapason.scope": service.scope,
    }
    provider.shutdown()


@pytest.mark.parametrize("response", ["http_error", "rpc_error", "tool_error", "timeout"])
def test_mcp_failures_are_marked_without_payloads(monkeypatch, response):
    import httpx
    import mcp_rpc
    from mcp_context import McpServerContext
    from opentelemetry.trace import StatusCode
    memory, provider = exporter()
    monkeypatch.setattr(mcp_rpc.trace, "get_tracer", provider.get_tracer)
    def handler(request):
        if response == "timeout":
            raise httpx.ReadTimeout("private content", request=request)
        if response == "http_error":
            return httpx.Response(503, text="private content")
        body = {"error": {"message": "private content"}} if response == "rpc_error" else {
            "result": {"isError": True, "content": [{"text": "private content"}]},
        }
        return httpx.Response(200, json=body)
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(RuntimeError):
        mcp_rpc.mcp_call_tool_json(McpServerContext("default", "Diapason", "https://mcp.example/?secret=hidden"), "resolveReferences", {"trade_xml": "private content"})
    span = memory.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["server.address"] == "mcp.example"
    assert span.events == () and span.status.description is None
    assert "private" not in str(span.attributes) and "secret" not in str(span.attributes)
    provider.shutdown()


def test_http_internal_error_sets_error_status(service):
    from fastapi.testclient import TestClient
    from opentelemetry.trace import StatusCode
    memory, provider = exporter()
    service.runtime.tracer = provider.get_tracer("capture")
    @service.app.get("/api/broken")
    def broken():
        raise RuntimeError("private content")
    with TestClient(service.app, raise_server_exceptions=False) as client:
        assert client.get("/api/broken").status_code == 500
    span = memory.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["http.response.status_code"] == 500
    assert span.attributes["error.type"] == "RuntimeError"
    assert span.events == () and span.status.description is None
    provider.shutdown()