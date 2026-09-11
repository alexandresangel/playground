import logging

import pytest
from fastapi import APIRouter, HTTPException
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from langsmith import get_tracing_context

from pascal.observability import ai
from pascal.observability.routing import quiet_access


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
    caplog.set_level(logging.WARNING, logger="diapason.chat")
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


def test_quiet_endpoint_metadata_works_with_router_prefix(service, caplog):
    router = APIRouter()
    @router.get("/ping")
    @quiet_access
    def ping():
        return {"ok": True}
    service.app.include_router(router, prefix="/api/other")
    caplog.set_level(logging.INFO, logger="diapason.chat")
    assert service.client.get("/api/other/ping").status_code == 200
    assert not [record for record in caplog.records if record.name == "diapason.chat"]
