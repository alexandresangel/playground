"""Offline Capture feature tests: real PDF parsing and LangGraph, mocked Azure/MCP.

These preserve ai-agent's PDF -> model XML -> resolveReferences contract while
testing the compiled Capture workflow rather than replacing it with a stub.
"""

import asyncio
from pathlib import Path
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import pytest

from capture.workflow import graph, prompts

PDF = Path(__file__).parent / "fixtures/sample-loan-contract.pdf"
CATALOG = Path(__file__).parents[1] / "config/catalog.json"


def run(workflow, **kwargs):
    return asyncio.run(graph.run_capture(
        pdf_bytes=kwargs.pop("pdf_bytes", PDF.read_bytes()),
        trade_type=kwargs.pop("trade_type", "iamLoan"),
        cluster=workflow.cluster, config=workflow.config, azure=workflow.azure, **kwargs,
    ))


@pytest.mark.parametrize("trade_type,prompt,view_entity,menu_name", [
    ("iamLoan", "mltLoan.txt", "loanDeposit", "loanDeposit"),
    ("buyDiscountedPaper", "buyDiscountedPaper.txt", "commercialPaper", "commercialPaper"),
    ("commercialLease", "commercialLeaseClassic.txt", "loanDeposit", "commercialLease"),
], ids=["loan", "commercial-paper", "lease-with-distinct-menu"])
def test_pdf_to_resolved_xml_preserves_original_contract(workflow, trade_type, prompt, view_entity, menu_name):
    resolved_xml = f'<trade><tradeType shortname="{trade_type}"/><amount>456</amount><entity name="Bank"/></trade>'
    workflow.resolver.return_value["trade_xml"] = resolved_xml
    result = run(workflow, trade_type=trade_type, debug=True)

    workflow.completion.assert_called_once()
    call = workflow.completion.call_args.kwargs
    assert call["model"] == "same-model"
    assert call["temperature"] == 0.5
    assert call["messages"][0] == {"role": "system", "content": (CATALOG.parent / "prompts" / prompt).read_text(encoding="utf-8")}
    instruction, document = call["messages"][1]["content"].split("\n\n", 1)
    assert instruction == "Extract the trade as Diapason import XML from this document text. Return XML only."
    assert document.strip()
    assert result["debug"]["extract"]["pdf_text_length"] == len(document)

    workflow.resolver.assert_called_once()
    args, kw = workflow.resolver.call_args
    assert args[:2] == (workflow.cluster.diapason, "resolveReferences")
    assert kw == {"timeout_s": 180.0}
    source_xml = args[2]["trade_xml"]
    source = ET.fromstring(source_xml)
    assert source.find("tradeType").attrib["shortname"] == trade_type
    assert source.findtext("amount") == "123"
    assert args[2] == {"view_entity": view_entity, "trade_xml": source_xml}

    assert result["success"] is True
    assert result["trade_type"] == trade_type
    assert result["view_entity"] == view_entity
    assert result["menu_name"] == menu_name
    assert result["trade_xml"] == resolved_xml
    assert result["extracted_field_count"] == 3
    assert result["warnings"] == ["review"]
    assert result["message"] == ""
    assert "session_artifacts" not in result
    assert result["debug"]["extract"]["trade_xml"] == source_xml
    assert result["debug"]["resolve_references_request"] == args[2]
    assert result["debug"]["resolve_references"] == workflow.resolver.return_value
    assert [entry["tool"] for entry in result["tool_trace"]] == ["extract_xml", "resolveReferences"]
    assert set(result["timings_ms"]) == {"extract", "resolve"}
    assert all(isinstance(value, int) and value >= 0 for value in result["timings_ms"].values())


def test_langgraph_runs_validation_extraction_resolution_and_result_in_order(workflow):
    async def collect_updates():
        compiled = graph.create_capture_graph(
            cluster=workflow.cluster, config=workflow.config, azure=workflow.azure, debug=False,
        )
        return [update async for update in compiled.astream(
            {"pdf_bytes": PDF.read_bytes(), "trade_type": "iamLoan"},
            config={"callbacks": []}, stream_mode="updates",
        )]

    # Use the same privacy context as run_capture: LangSmith must stay disabled.
    with graph.private_graph_run():
        updates = asyncio.run(collect_updates())
    assert [list(update) for update in updates] == [["validate"], ["extract"], ["resolve"], ["result"]]
    extracted_xml = updates[1]["extract"]["extract"]["trade_xml"]
    assert workflow.resolver.call_args.args[2]["trade_xml"] == extracted_xml
    result = updates[3]["result"]["result"]
    assert result["trade_xml"] == updates[2]["resolve"]["resolve_body"]["trade_xml"]
    assert result["success"] is True
    assert "debug" not in result


@pytest.mark.parametrize("pdf,error", [(b"", "empty"), (b"not pdf", "not a PDF"), (b"%PDF-" + b"x" * 50, "max size")])
def test_validation_precedes_catalog_and_model(workflow, pdf, error, monkeypatch):
    workflow.config["capture"]["max_pdf_bytes"] = 20
    lookup = Mock(side_effect=AssertionError("catalog should not be read"))
    monkeypatch.setattr(graph, "get_trade_type_config", lookup)
    with pytest.raises(ValueError, match=error):
        run(workflow, pdf_bytes=pdf)
    lookup.assert_not_called()
    workflow.completion.assert_not_called()
    workflow.resolver.assert_not_called()


@pytest.mark.parametrize("body,message", [
    ({"success": True}, "resolveReferences returned success but no trade_xml"),
    ({"success": False, "message": "unresolved", "warnings": ["missing"]}, "unresolved"),
    ({"success": False, "trade_xml": "<trade><amount>123</amount></trade>", "message": "partial"}, "partial"),
], ids=["success-without-xml", "business-failure", "partial-xml-is-not-success"])
def test_resolver_business_failure_returns_unsuccessful_result(workflow, body, message):
    workflow.resolver.return_value = body
    result = run(workflow)
    assert result["success"] is False
    assert result["extracted_field_count"] == 0
    assert result["message"] == message
    assert result["trade_xml"] == body.get("trade_xml", "")
    assert "debug" not in result
    assert "session_artifacts" not in result
    assert result["warnings"] == body.get("warnings", [])


@pytest.mark.parametrize("content,error", [("", RuntimeError), ("not XML", ValueError), ("<broken", ValueError)],
                         ids=["empty-response", "no-xml", "malformed-xml"])
def test_bad_model_output_never_resolves(workflow, content, error):
    workflow.completion.return_value.choices[0].message.content = content
    with pytest.raises(error):
        run(workflow)
    workflow.resolver.assert_not_called()


def test_missing_trade_type_stops_before_model_and_resolver(workflow):
    with pytest.raises(ValueError, match="trade_type is required"):
        run(workflow, trade_type=" ")
    workflow.completion.assert_not_called()
    workflow.resolver.assert_not_called()


def test_unknown_trade_type_without_default_stops_before_model(workflow, monkeypatch):
    monkeypatch.setattr(prompts, "_catalog", {"prompts": {}})
    with pytest.raises(ValueError, match="Unknown trade_type"):
        run(workflow, trade_type="unconfigured")
    workflow.completion.assert_not_called()
    workflow.resolver.assert_not_called()


def test_model_error_stops_before_reference_resolution(workflow):
    workflow.completion.side_effect = RuntimeError("model unavailable")
    with pytest.raises(RuntimeError, match="model unavailable"):
        run(workflow)
    workflow.completion.assert_called_once()
    workflow.resolver.assert_not_called()


def test_resolver_transport_error_propagates_without_repeating_extraction(workflow):
    workflow.resolver.side_effect = RuntimeError("resolver unavailable")
    with pytest.raises(RuntimeError, match="resolver unavailable"):
        run(workflow)
    workflow.completion.assert_called_once()
    workflow.resolver.assert_called_once()
