import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from capture.workflow import extract_xml, graph, prompts
from mcp_context import McpCluster, McpServerContext

PDF = Path(__file__).parent / "fixtures/sample-loan-contract.pdf"
CATALOG = Path(__file__).parents[1] / "config/catalog.json"


@pytest.fixture
def workflow(monkeypatch):
    monkeypatch.setattr(prompts, "_catalog", json.loads(CATALOG.read_text()))
    monkeypatch.setattr(prompts, "_prompt_cache", {})
    monkeypatch.setattr(prompts, "_catalog_version", "")
    reads = Mock(return_value="original extraction prompt")
    monkeypatch.setattr(prompts, "read_blob_text", reads)
    completion = Mock(return_value=NS(
        choices=[NS(message=NS(content='```xml\n<trade><tradeType shortname="wrong"/><amount>123</amount></trade>\n```'))],
        usage=NS(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    ))
    client = NS(chat=NS(completions=NS(create=completion)))
    resolver = Mock(return_value={"success": True, "trade_xml": '<trade><tradeType shortname="iamLoan"/><amount>123</amount></trade>', "warnings": ["review"]})
    monkeypatch.setattr(graph, "mcp_call_tool_json", resolver)
    config = {"storage": {"account_name": "test"}, "intelligence_contract": {"temperature": 0.5}}
    cluster = McpCluster((McpServerContext("default", "Diapason", "https://mcp.example", {"Authorization": "caller"}),))
    return NS(config=config, cluster=cluster, azure={"client": client, "deployment": "same-model"}, completion=completion, resolver=resolver, reads=reads)


def run(workflow, **kwargs):
    return asyncio.run(graph.run_capture(pdf_bytes=kwargs.pop("pdf_bytes", PDF.read_bytes()), trade_type=kwargs.pop("trade_type", "iamLoan"), cluster=workflow.cluster, config=workflow.config, azure=workflow.azure, **kwargs))


def test_pdf_to_xml_and_original_resolver_contract(workflow):
    result = run(workflow, debug=True)
    call = workflow.completion.call_args.kwargs
    assert call["model"] == "same-model" and call["temperature"] == 0.5
    assert call["messages"][0] == {"role": "system", "content": "original extraction prompt"}
    assert call["messages"][1]["content"].startswith("Extract the trade as Diapason import XML from this document text. Return XML only.\n\n")
    assert result["success"] and result["trade_type"] == "iamLoan"
    args, kw = workflow.resolver.call_args
    assert args[:2] == (workflow.cluster.diapason, "resolveReferences")
    assert kw == {"timeout_s": 180.0}
    assert 'shortname="iamLoan"' in args[2]["trade_xml"]
    assert result["session_artifacts"]["source_trade_xml"] == args[2]["trade_xml"]
    assert result["debug"]["resolve_references_request"] == args[2]
    assert [t["tool"] for t in result["tool_trace"]] == ["extract_xml", "resolveReferences"]


@pytest.mark.parametrize("pdf,error", [(b"", "empty"), (b"not pdf", "not a PDF"), (b"%PDF-" + b"x" * 50, "max size")])
def test_validation_precedes_catalog_and_model(workflow, pdf, error, monkeypatch):
    workflow.config["intelligence_contract"]["max_pdf_bytes"] = 20
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
    assert result["session_artifacts"]["resolve_references"] == body


@pytest.mark.parametrize("content,error", [("", RuntimeError), ("not XML", ValueError), ("<broken", ValueError)])
def test_bad_model_output_never_resolves(workflow, content, error):
    workflow.completion.return_value.choices[0].message.content = content
    with pytest.raises(error):
        run(workflow)
    workflow.resolver.assert_not_called()


def test_catalog_refresh_and_cache_invalidation(workflow):
    text = CATALOG.read_text()
    workflow.reads.side_effect = [text, "first prompt", text, "new prompt"]
    first = prompts.init_capture_prompts(workflow.config)
    assert isinstance(first["version"], str) and first["version"]
    assert prompts.get_prompt_text(workflow.config, "prompts/mltLoan.txt") == "first prompt"
    assert prompts.get_prompt_text(workflow.config, "prompts/mltLoan.txt") == "first prompt"
    assert prompts.refresh_capture_prompts(workflow.config) == first
    assert prompts.get_prompt_text(workflow.config, "prompts/mltLoan.txt") == "new prompt"
    assert prompts.capture_prompt_version() == first["version"]
    assert workflow.reads.call_args.args == ("test", "agent-config", "skills/intelligence-contract/prompts/mltLoan.txt")
