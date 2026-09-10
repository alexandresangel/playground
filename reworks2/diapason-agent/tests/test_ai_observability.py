import asyncio
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from pascal.observability import ai as ai_observability
from pascal.compat.capture import extract_xml, prompts, graph as workflow


@pytest.fixture
def spans(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(ai_observability, "get_tracer", lambda name: provider.get_tracer(name))
    yield provider, exporter
    provider.shutdown()


def test_content_free_failure_and_correlation(spans):
    provider, exporter = spans
    with provider.get_tracer("company").start_as_current_span("http.request") as parent:
        with pytest.raises(ValueError):
            with ai_observability.ai_span("ai.capture.model"):
                raise ValueError("secret JWT prompt PDF XML tool payload")
    child = next(s for s in exporter.get_finished_spans() if s.name == "ai.capture.model")
    assert child.parent.span_id == parent.get_span_context().span_id
    assert child.attributes["ai.outcome"] == "error"
    assert child.attributes["ai.duration_ms"] >= 0
    assert child.events == ()
    assert "secret" not in str(child.attributes) + str(child.status.description)


def test_capture_spans_tokens_and_disabled_payload_tracing(spans, monkeypatch):
    from langsmith import utils
    provider, exporter = spans
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    client = MagicMock()

    def create(**kwargs):
        assert not utils.tracing_is_enabled()
        return NS(choices=[NS(message=NS(content="<trade/>"))], usage=NS(prompt_tokens=9, completion_tokens=3, total_tokens=12))

    client.chat.completions.create.side_effect = create
    monkeypatch.setattr(prompts, "_catalog", {"default_prompt": "prompt.txt"})
    monkeypatch.setattr(extract_xml, "get_prompt_text", lambda *a: "private prompt")
    monkeypatch.setattr(extract_xml, "pdf_to_text", lambda *a: "private PDF")
    monkeypatch.setattr(workflow, "mcp_call_tool_json", lambda *a, **k: {"success": True, "trade_xml": "<trade/>"})
    with provider.get_tracer("company").start_as_current_span("http.request") as parent:
        asyncio.run(workflow.run_capture(pdf_bytes=b"%PDF-private", trade_type="loan", config={},
            azure={"client": client, "deployment": "same"}, cluster=NS(diapason=NS(server_id="default", label="Diapason"))))
    emitted = exporter.get_finished_spans()
    model = next(s for s in emitted if s.name == "ai.capture.model")
    assert model.attributes["gen_ai.usage.input_tokens"] == 9
    assert model.attributes["gen_ai.usage.output_tokens"] == 3
    assert {s.name for s in emitted} >= {"ai.capture.workflow", "ai.capture.validate", "ai.capture.extract", "ai.capture.tool"}
    assert all(s.context.trace_id == parent.get_span_context().trace_id for s in emitted)
    assert "private" not in str([(s.attributes, s.events) for s in emitted])


def test_ai_http_error_logs_do_not_contain_payload(offline, monkeypatch, caplog):
    from fastapi import HTTPException
    from starlette.requests import Request
    request = Request({"type": "http", "method": "POST", "path": "/api/skills/intelligence-contract", "headers": []})
    response = asyncio.run(offline.app.exception_handlers[HTTPException](request, HTTPException(502, detail="private-tool-xml")))
    assert b"private-tool-xml" in response.body  # Original public error contract.
    assert "private-tool-xml" not in caplog.text
