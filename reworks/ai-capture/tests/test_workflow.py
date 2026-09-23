import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from capture.workflow import graph, prompts
from mcp_context import McpCluster, McpServerContext

PDF = Path(__file__).parent / "fixtures/sample-loan-contract.pdf"
CATALOG = Path(__file__).parents[1] / "config/catalog.json"


@pytest.fixture
def workflow(monkeypatch):
    monkeypatch.setattr(prompts, "_catalog", json.loads(CATALOG.read_text()))
    monkeypatch.setattr(prompts, "_prompt_cache", {})
    monkeypatch.setattr(prompts, "_catalog_version", "")
    monkeypatch.setattr(prompts, "_config_dir", CATALOG.parent)
    completion = Mock(return_value=NS(
        choices=[NS(message=NS(content='```xml\n<trade><tradeType shortname="wrong"/><amount>123</amount></trade>\n```'))],
        usage=NS(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    ))
    client = NS(chat=NS(completions=NS(create=completion)))
    resolver = Mock(return_value={"success": True, "trade_xml": '<trade><tradeType shortname="iamLoan"/><amount>123</amount></trade>', "warnings": ["review"]})
    monkeypatch.setattr(graph, "mcp_call_tool_json", resolver)
    config = {"capture": {"temperature": 0.5}}
    cluster = McpCluster((McpServerContext("default", "Diapason", "https://mcp.example", {"Authorization": "caller"}),))
    return NS(config=config, cluster=cluster, azure={"client": client, "deployment": "same-model"}, completion=completion, resolver=resolver)


def run(workflow, **kwargs):
    return asyncio.run(graph.run_capture(pdf_bytes=kwargs.pop("pdf_bytes", PDF.read_bytes()), trade_type=kwargs.pop("trade_type", "iamLoan"), cluster=workflow.cluster, config=workflow.config, azure=workflow.azure, **kwargs))


def test_pdf_to_xml_and_original_resolver_contract(workflow):
    result = run(workflow, debug=True)
    call = workflow.completion.call_args.kwargs
    assert call["model"] == "same-model" and call["temperature"] == 0.5
    assert call["messages"][0] == {"role": "system", "content": (CATALOG.parent / "prompts/mltLoan.txt").read_text(encoding="utf-8")}
    assert call["messages"][1]["content"].startswith("Extract the trade as Diapason import XML from this document text. Return XML only.\n\n")
    assert result["success"] and result["trade_type"] == "iamLoan"
    args, kw = workflow.resolver.call_args
    assert args[:2] == (workflow.cluster.diapason, "resolveReferences")
    assert kw == {"timeout_s": 180.0}
    assert 'shortname="iamLoan"' in args[2]["trade_xml"]
    assert "session_artifacts" not in result
    assert result["debug"]["extract"]["trade_xml"] == args[2]["trade_xml"]
    assert "tool_trace" not in result and "timings_ms" not in result
    assert result["debug"]["resolve_references_request"] == args[2]


@pytest.mark.parametrize("pdf,error", [(b"", "empty"), (b"not pdf", "not a PDF"), (b"%PDF-" + b"x" * 50, "max size")])
def test_validation_precedes_catalog_and_model(workflow, pdf, error, monkeypatch):
    workflow.config["capture"]["max_pdf_bytes"] = 20
    lookup = Mock(side_effect=AssertionError("catalog should not be read"))
    monkeypatch.setattr(graph, "get_trade_type_config", lookup)
    with pytest.raises(ValueError, match=error):
        run(workflow, pdf_bytes=pdf)
    workflow.completion.assert_not_called()
    workflow.resolver.assert_not_called()


@pytest.mark.parametrize("body", [{"success": True}, {"success": False, "message": "unresolved", "warnings": ["missing"]}])
def test_resolver_failure_result(workflow, body):
    workflow.resolver.return_value = body
    result = run(workflow)
    assert result["success"] is False and result["extracted_field_count"] == 0
    assert "debug" not in result
    assert "session_artifacts" not in result
    assert result["warnings"] == body.get("warnings", [])


@pytest.mark.parametrize("content,error", [("", RuntimeError), ("not XML", ValueError), ("<broken", ValueError)])
def test_bad_model_output_never_resolves(workflow, content, error):
    workflow.completion.return_value.choices[0].message.content = content
    with pytest.raises(error):
        run(workflow)
    workflow.resolver.assert_not_called()


def test_catalog_refresh_and_cache_invalidation(workflow, tmp_path):
    config_dir = tmp_path / "config"
    (config_dir / "prompts").mkdir(parents=True)
    (config_dir / "catalog.json").write_bytes(CATALOG.read_bytes())
    prompt = config_dir / "prompts/mltLoan.txt"
    prompt.write_text("first prompt", encoding="utf-8")
    first = prompts.init_capture_prompts(workflow.config, tmp_path)
    assert isinstance(first["version"], str) and first["version"]
    assert first["source"] == str(config_dir / "catalog.json")
    assert prompts.get_prompt_text(workflow.config, "prompts/mltLoan.txt") == "first prompt"
    prompt.write_text("new prompt", encoding="utf-8")
    assert prompts.get_prompt_text(workflow.config, "prompts/mltLoan.txt") == "first prompt"
    assert prompts.refresh_capture_prompts(workflow.config, tmp_path) == first
    assert prompts.get_prompt_text(workflow.config, "prompts/mltLoan.txt") == "new prompt"
    assert prompts.capture_prompt_version() == first["version"]


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
    assert run(workflow)["success"] is False
    span = next(s for s in memory.get_finished_spans() if s.name == "ai.capture.workflow")
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["ai.outcome"] == "error"
    assert span.attributes["ai.result_success"] is False
    assert "private" not in str(span.attributes)
    provider.shutdown()
