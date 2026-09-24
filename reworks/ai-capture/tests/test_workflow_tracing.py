"""Offline trace propagation/privacy across HTTP, LangGraph, model and resolver."""

import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest

from capture.workflow import graph

PDF = Path(__file__).parent / "fixtures/sample-loan-contract.pdf"


@pytest.mark.parametrize("incoming", [None, "invalid", "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"])
def test_http_workflow_model_and_mcp_share_trace(service, workflow, monkeypatch, incoming):
    import httpx
    import mcp_rpc
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import SpanKind
    from capture.observability import ai

    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    service.runtime.tracer = provider.get_tracer("capture")
    monkeypatch.setattr(ai, "get_tracer", provider.get_tracer)
    monkeypatch.setattr(mcp_rpc.trace, "get_tracer", provider.get_tracer)
    monkeypatch.setattr(graph, "mcp_call_tool_json", mcp_rpc.mcp_call_tool_json)
    client = Mock(chat=workflow.azure["client"].chat)
    monkeypatch.setattr(service.runtime, "azure_client", lambda: {"client": client, "deployment": "same-model"})
    requests = []
    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {
            "structuredContent": {"success": True, "trade_xml": "<trade><amount>123</amount></trade>"},
        }})
    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(transport), **kw))
    headers = {**service.headers, "X-Diapason-Chat-Session": "trace-test"}
    if incoming:
        headers["traceparent"] = incoming
        headers["tracestate"] = "vendor=value"
    response = service.client.post("/api/capture", headers=headers, data={"trade_type": "iamLoan"},
        files={"pdf": ("loan.pdf", PDF.read_bytes(), "application/pdf")})
    assert response.status_code == 200
    spans = {s.name: s for s in memory.get_finished_spans()}
    http = spans["http.request"]
    assert http.kind == SpanKind.SERVER
    assert http.attributes["http.route"] == "/api/capture"
    assert http.attributes["diapason.session_id"] == "trace-test"
    if incoming and incoming.startswith("00-"):
        assert http.context.trace_id == int(incoming.split("-")[1], 16)
        assert http.parent.span_id == int(incoming.split("-")[2], 16)
        assert requests[0].headers["tracestate"] == "vendor=value"
    else:
        assert http.parent is None
    for child, parent in (("capture.request", "http.request"), ("ai.capture.workflow", "capture.request"),
                          ("ai.capture.validate", "ai.capture.workflow"),
                          ("ai.capture.extract", "ai.capture.workflow"),
                          ("ai.capture.resolve", "ai.capture.workflow"),
                          ("ai.capture.model", "ai.capture.extract"), ("mcp.request", "ai.capture.resolve")):
        assert spans[child].parent.span_id == spans[parent].context.span_id
    assert len({s.context.trace_id for s in spans.values()}) == 1
    assert all(s.instrumentation_scope.name == "capture" for s in spans.values())
    model, rpc = spans["ai.capture.model"], spans["mcp.request"]
    assert model.kind == rpc.kind == SpanKind.CLIENT
    assert model.attributes["gen_ai.request.model"] == "same-model"
    assert model.attributes["gen_ai.usage.total_tokens"] == 18
    assert rpc.attributes["gen_ai.tool.name"] == "resolveReferences"
    assert requests[0].headers["traceparent"] == f"00-{rpc.context.trace_id:032x}-{rpc.context.span_id:016x}-{int(rpc.context.trace_flags):02x}"
    assert "tool_trace" not in response.json()
    exported = str([(dict(s.attributes), s.events, s.status.description) for s in spans.values()])
    for private in ("private-api-token", "<trade>", "Extract the trade", "Bearer", "trade_xml"):
        assert private not in exported
    provider.shutdown()


def test_business_failure_marks_workflow_span(workflow, monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode
    from capture.observability import ai
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    monkeypatch.setattr(ai, "get_tracer", provider.get_tracer)
    workflow.resolver.return_value = {"success": False, "message": "private document content"}
    result = asyncio.run(graph.run_capture(
        pdf_bytes=PDF.read_bytes(), trade_type="iamLoan", cluster=workflow.cluster,
        config=workflow.config, azure=workflow.azure,
    ))
    assert result["success"] is False
    span = next(s for s in memory.get_finished_spans() if s.name == "ai.capture.workflow")
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["ai.outcome"] == "error"
    assert span.attributes["ai.result_success"] is False
    assert "private" not in str(span.attributes)
    provider.shutdown()
