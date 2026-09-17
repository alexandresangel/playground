"""The compiled graph executes validate -> extract -> resolve -> result."""

import asyncio
import xml.etree.ElementTree as ET

import pytest

from capture.workflow import graph, prompts

pytestmark = pytest.mark.asyncio


async def test_graph_streams_all_four_steps_in_order(workflow):
    compiled = graph.create_capture_graph(
        cluster=workflow.cluster, config=workflow.config, azure=workflow.azure, debug=False
    )
    updates = [
        update
        async for update in compiled.astream(
            {"pdf_bytes": workflow.pdf_bytes, "trade_type": "iamLoan"},
            config={"callbacks": []},
            stream_mode="updates",
        )
    ]
    assert [next(iter(update)) for update in updates] == [
        "validate",
        "extract",
        "resolve",
        "result",
    ]
    validate, extract, resolve, result = [next(iter(update.values())) for update in updates]
    assert validate == {"view_entity": "loanDeposit", "menu_name": "loanDeposit", "tool_trace": []}
    assert extract["extract"]["pdf_text_length"] > 0
    assert len(extract["tool_trace"]) == 1
    assert resolve["resolve_body"] == workflow.resolver.return_value
    assert len(resolve["tool_trace"]) == 2
    assert result["result"]["success"] is True


async def test_pdf_to_resolved_xml_preserves_capture_contract(workflow):
    result = await workflow.run(debug=True)
    call = workflow.completion.call_args.kwargs
    assert call["model"] == "same-model"
    assert call["temperature"] == 0.5
    assert call["messages"][0] == {
        "role": "system",
        "content": prompts.get_prompt_text(workflow.config, "prompts/mltLoan.txt"),
    }
    document = result["debug"]["extract"]["pdf_text_preview"]
    assert document
    assert call["messages"][1]["role"] == "user"
    prefix = (
        "Extract the trade as Diapason import XML from this document text. Return XML only.\n\n"
    )
    assert call["messages"][1]["content"].startswith(prefix + document)
    assert (
        len(call["messages"][1]["content"]) - len(prefix)
        == result["debug"]["extract"]["pdf_text_length"]
    )
    workflow.completion.assert_called_once()
    workflow.resolver.assert_called_once()
    args, kwargs = workflow.resolver.call_args
    assert args[:2] == (workflow.cluster.diapason, "resolveReferences")
    assert kwargs == {"timeout_s": 180.0}
    assert ET.fromstring(args[2]["trade_xml"]).find("tradeType").get("shortname") == "iamLoan"
    assert result["debug"]["extract"]["trade_xml"] == args[2]["trade_xml"]
    assert result["debug"]["resolve_references_request"] == args[2]
    assert result["debug"]["resolve_references"] == workflow.resolver.return_value
    assert result["tool_trace"][0]["arguments"]["prompt_path"] == "prompts/mltLoan.txt"
    assert [entry["tool"] for entry in result["tool_trace"]] == ["extract_xml", "resolveReferences"]
    assert result["trade_xml"] == workflow.resolver.return_value["trade_xml"]
    assert result["extracted_field_count"] == 2
    assert result["warnings"] == ["review"]
    assert "session_artifacts" not in result


async def test_concurrent_runs_do_not_share_result_or_trace_state(workflow):
    workflow.resolver.side_effect = lambda server, name, arguments, **kwargs: {
        "success": True,
        "trade_xml": arguments["trade_xml"],
    }
    results = await asyncio.gather(
        workflow.run(trade_type="iamLoan"), workflow.run(trade_type="commercialLease")
    )
    for result, trade_type, menu in zip(
        results, ["iamLoan", "commercialLease"], ["loanDeposit", "commercialLease"]
    ):
        assert result["trade_type"] == trade_type
        assert result["menu_name"] == menu
        assert ET.fromstring(result["trade_xml"]).find("tradeType").get("shortname") == trade_type
        assert len(result["tool_trace"]) == 2
        assert all(entry["arguments"]["trade_type"] == trade_type for entry in result["tool_trace"])
    assert results[0]["tool_trace"] is not results[1]["tool_trace"]
