"""Content-free HTTP and AI telemetry across the real Capture workflow."""

import logging
import pytest
from fastapi import APIRouter, HTTPException
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from langsmith import get_tracing_context, tracing_context

from capture.observability import ai
from capture.observability.http import apply_identity_span_attrs


@pytest.fixture
def span_exporter(monkeypatch):
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    monkeypatch.setattr(ai, "get_tracer", lambda name: provider.get_tracer(name))
    yield memory, provider
    provider.shutdown()


def test_ai_spans_record_usage_and_redact_exception(span_exporter):
    memory, provider = span_exporter
    with pytest.raises(ValueError):
        with ai.ai_span("ai.test.model") as span:
            ai.record_usage(span, {"input": 5, "output": 2, "total": 7})
            raise ValueError("private PDF and prompt")
    result = memory.get_finished_spans()[0]
    assert result.attributes["gen_ai.usage.total_tokens"] == 7
    assert result.attributes["ai.outcome"] == "error" and result.attributes["ai.duration_ms"] >= 0
    assert result.events == () and result.status.description is None
    assert "private" not in str(result.attributes)


def test_graph_tracing_disabled_per_context(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    with tracing_context(enabled=True):
        with pytest.raises(ValueError):
            with ai.private_graph_run():
                assert get_tracing_context()["enabled"] is False
                raise ValueError("workflow failed")
        assert get_tracing_context()["enabled"] is True


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


def test_incoming_trace_is_parent_of_http_span(service, span_exporter):
    memory, provider = span_exporter
    service.runtime.tracer = provider.get_tracer("http")
    trace_id = "0123456789abcdef0123456789abcdef"
    parent_id = "0123456789abcdef"
    response = service.client.get(
        "/api/health", headers={"traceparent": f"00-{trace_id}-{parent_id}-01"}
    )
    assert response.status_code == 200
    result = memory.get_finished_spans()[0]
    assert result.context.trace_id == int(trace_id, 16)
    assert result.parent.span_id == int(parent_id, 16)


def test_correlation_spans_have_no_storage_links(service, span_exporter):
    memory, provider = span_exporter
    with provider.get_tracer("http").start_as_current_span("capture.completion") as span:
        apply_identity_span_attrs(
            service.runtime,
            span,
            customer_id=7,
            user_id=42,
            session_id="pascal-session",
            scope=service.scope,
        )
    attrs = dict(memory.get_finished_spans()[0].attributes)
    assert attrs == {
        "diapason.customer_id": "7",
        "enduser.id": "42",
        "diapason.user_id": "42",
        "diapason.session_id": "pascal-session",
        "diapason.scope": service.scope,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_workflow_spans_record_stage_outcomes_and_usage_without_content(
    workflow, span_exporter, caplog, success
):
    memory, _ = span_exporter
    workflow.resolver.return_value = {
        "success": success,
        "trade_xml": "<trade><amount>123</amount></trade>",
        "message": "PRIVATE-RESOLVER-MESSAGE",
    }
    caplog.set_level(logging.INFO, logger="diapason.chat")
    result = await workflow.run(debug=True)
    spans = {span.name: span for span in memory.get_finished_spans()}
    assert set(spans) == {
        "ai.capture.workflow",
        "ai.capture.validate",
        "ai.capture.extract",
        "ai.capture.model",
        "ai.capture.tool",
    }
    parent = spans["ai.capture.workflow"]
    assert parent.attributes["ai.result_success"] is success
    assert all(span.attributes["ai.outcome"] == "success" for span in spans.values())
    for name in ("ai.capture.validate", "ai.capture.extract", "ai.capture.tool"):
        assert spans[name].parent.span_id == parent.context.span_id
    assert spans["ai.capture.model"].parent.span_id == spans["ai.capture.extract"].context.span_id
    assert spans["ai.capture.model"].attributes["gen_ai.usage.input_tokens"] == 11
    assert spans["ai.capture.model"].attributes["gen_ai.usage.output_tokens"] == 7
    assert spans["ai.capture.model"].attributes["gen_ai.usage.total_tokens"] == 18
    for span in spans.values():
        assert span.events == ()
        assert span.status.description is None
        exported = str(span.attributes)
        for sensitive in (
            "PRIVATE-RESOLVER-MESSAGE",
            "<trade>",
            result["debug"]["extract"]["pdf_text_preview"],
        ):
            assert sensitive not in exported
            assert sensitive not in caplog.text


@pytest.mark.asyncio
async def test_model_failure_marks_workflow_and_extract_spans_without_exception_text(
    workflow, span_exporter
):
    memory, _ = span_exporter
    workflow.completion.side_effect = RuntimeError("PRIVATE-DOCUMENT-CONTENT")
    with pytest.raises(RuntimeError, match="PRIVATE-DOCUMENT-CONTENT"):
        await workflow.run()
    spans = {span.name: span for span in memory.get_finished_spans()}
    assert "ai.capture.tool" not in spans
    for name in ("ai.capture.workflow", "ai.capture.extract", "ai.capture.model"):
        span = spans[name]
        assert span.attributes["ai.outcome"] == "error"
        assert span.events == () and span.status.description is None
        assert "PRIVATE-DOCUMENT-CONTENT" not in str(span.attributes)


@pytest.mark.asyncio
async def test_graph_disables_tracing_inside_model_worker_and_restores_caller(workflow):
    response = workflow.completion.return_value

    def complete(**kwargs):
        assert get_tracing_context()["enabled"] is False
        return response

    workflow.completion.side_effect = complete
    with tracing_context(enabled=True):
        await workflow.run()
        assert get_tracing_context()["enabled"] is True


def test_record_usage_ignores_noninteger_and_boolean_values(span_exporter):
    memory, provider = span_exporter
    with provider.get_tracer("test").start_as_current_span("usage") as span:
        ai.record_usage(span, {"input": True, "output": "7", "total": 18})
    assert dict(memory.get_finished_spans()[0].attributes) == {"gen_ai.usage.total_tokens": 18}


@pytest.mark.parametrize("success", [True, False])
def test_upload_completion_span_records_identity_and_outcome_without_content(
    service, workflow, span_exporter, monkeypatch, caplog, success
):
    memory, provider = span_exporter
    service.runtime.tracer = provider.get_tracer("http")
    monkeypatch.setattr(service.runtime, "azure_client", lambda: workflow.azure)
    workflow.resolver.return_value["success"] = success
    workflow.resolver.return_value["message"] = "PRIVATE-RESOLVER-MESSAGE"
    caplog.set_level(logging.INFO, logger="diapason.chat")
    response = service.client.post(
        "/api/capture",
        headers=service.headers,
        data={"trade_type": "iamLoan", "session_id": "caller-session"},
        files={"pdf": ("contract.pdf", workflow.pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    assert "debug" not in response.json()
    spans = {span.name: span for span in memory.get_finished_spans()}
    completion = spans["capture.completion"]
    assert dict(completion.attributes) == {
        "diapason.customer_id": "7",
        "enduser.id": "42",
        "diapason.user_id": "42",
        "diapason.session_id": "caller-session",
        "diapason.scope": service.scope,
        "ai.result_success": success,
    }
    assert completion.parent.span_id == spans["http.request"].context.span_id
    assert spans["ai.capture.workflow"].parent.span_id == spans["http.request"].context.span_id
    assert spans["http.request"].attributes["http.status_code"] == 200
    assert spans["http.request"].attributes["diapason.session_id"] == "caller-session"
    for sensitive in ("PRIVATE-RESOLVER-MESSAGE", "<trade>", "private-api-token"):
        assert sensitive not in caplog.text
        assert all(sensitive not in str(span.attributes) for span in spans.values())
