import asyncio
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from capture.workflow import extract_xml, prompts, graph as workflow
from mcp_context import McpCluster, McpServerContext


@pytest.fixture
def capture_runtime(monkeypatch):
    order = []
    config = {"intelligence_contract": {"temperature": 0.5}}
    client = MagicMock()
    client.chat.completions.create.return_value = NS(
        choices=[NS(message=NS(content='```xml\n<trade><entity name="ACME"/><tradeType shortname="wrong"/></trade>\n```'))],
        usage=NS(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    )
    monkeypatch.setattr(prompts, "_catalog", {"default_prompt": "prompts/loan.txt", "default_view_entity": "loanDeposit"})
    monkeypatch.setattr(extract_xml, "get_prompt_text", lambda *args: order.append("prompt") or "original prompt\r\n")
    monkeypatch.setattr(extract_xml, "pdf_to_text", lambda data: order.append("pdf") or "private document")
    original_create = client.chat.completions.create.return_value
    client.chat.completions.create.side_effect = lambda **kwargs: order.append("model") or original_create
    cluster = McpCluster(servers=(McpServerContext("default", "Diapason", "https://mcp.test/mcp", {"Authorization": "scoped-secret"}),))
    resolve = MagicMock(side_effect=lambda *args, **kwargs: order.append("resolve") or {"success": True, "trade_xml": '<trade><amount>12</amount></trade>', "warnings": ["notice", "", None, 3]})
    monkeypatch.setattr(workflow, "mcp_call_tool_json", resolve)
    return NS(order=order, config=config, client=client, azure={"client": client, "deployment": "unchanged-deployment"}, cluster=cluster, resolve=resolve)


def run(runtime, **overrides):
    return asyncio.run(workflow.run_capture(**{
        "pdf_bytes": b"%PDF-test", "trade_type": "iamLoan", "cluster": runtime.cluster,
        "config": runtime.config, "azure": runtime.azure, **overrides,
    }))


def test_graph_order_model_parameters_and_explicit_trade_type(capture_runtime):
    runtime = capture_runtime
    result = run(runtime)
    assert runtime.order == ["prompt", "pdf", "model", "resolve"]
    call = runtime.client.chat.completions.create.call_args.kwargs
    assert call == {"model": "unchanged-deployment", "temperature": 0.5, "messages": [
        {"role": "system", "content": "original prompt\r\n"},
        {"role": "user", "content": "Extract the trade as Diapason import XML from this document text. Return XML only.\n\nprivate document"},
    ]}
    args, kwargs = runtime.resolve.call_args
    assert args[0] is runtime.cluster.diapason and args[1] == "resolveReferences"
    assert args[2]["view_entity"] == "loanDeposit"
    assert 'shortname="iamLoan"' in args[2]["trade_xml"] and 'shortname="wrong"' not in args[2]["trade_xml"]
    assert kwargs == {"timeout_s": 180.0}
    assert set(result) == {"success", "trade_xml", "view_entity", "menu_name", "trade_type", "extracted_field_count", "message", "warnings", "tool_trace", "session_artifacts", "timings_ms"}
    assert result["warnings"] == ["notice", "3"]
    assert "debug" not in result
    assert result["tool_trace"][0]["name"] == "intelligence-contract"


@pytest.mark.parametrize("data,limit,message", [
    (b"", 100, "PDF file is empty"),
    (b"invalid-too-big", 2, "PDF exceeds max size (2 bytes)"),
    (b"invalid", 100, "File is not a PDF (%PDF- header missing)"),
])
def test_pdf_errors_precede_trade_type_errors(capture_runtime, data, limit, message):
    capture_runtime.config["intelligence_contract"]["max_pdf_bytes"] = limit
    with pytest.raises(ValueError) as caught:
        run(capture_runtime, pdf_bytes=data, trade_type="")
    assert str(caught.value) == message
    assert capture_runtime.order == []


def test_trade_type_error_precedes_prompt_and_pdf(capture_runtime):
    with pytest.raises(ValueError, match="trade_type is required"):
        run(capture_runtime, trade_type="")
    assert capture_runtime.order == []


def test_prompt_error_precedes_pdf(capture_runtime, monkeypatch):
    def fail(*args):
        raise RuntimeError("missing prompt")
    monkeypatch.setattr(extract_xml, "get_prompt_text", fail)
    with pytest.raises(RuntimeError, match="missing prompt"):
        run(capture_runtime)
    assert capture_runtime.order == []


@pytest.mark.parametrize("content,message", [("", "Empty LLM response"), ("not XML", "did not contain XML"), ("<trade>", "Invalid trade XML")])
def test_invalid_model_output_never_resolves(capture_runtime, content, message):
    capture_runtime.client.chat.completions.create.side_effect = None
    capture_runtime.client.chat.completions.create.return_value = NS(choices=[NS(message=NS(content=content))])
    with pytest.raises((RuntimeError, ValueError), match=message):
        run(capture_runtime)
    capture_runtime.resolve.assert_not_called()


def test_resolver_failure_and_debug_shape(capture_runtime):
    capture_runtime.resolve.side_effect = None
    capture_runtime.resolve.return_value = {"success": True, "trade_xml": " "}
    result = run(capture_runtime, debug=True)
    assert result["success"] is False
    assert result["message"] == "resolveReferences returned success but no trade_xml"
    assert result["extracted_field_count"] == 0
    assert result["debug"]["extract"] == result["session_artifacts"]["extract"]
    assert result["debug"]["resolve_references_request"]["trade_xml"] == result["session_artifacts"]["source_trade_xml"]


def test_catalog_fallback_is_preserved(capture_runtime):
    result = run(capture_runtime, trade_type="not-in-catalog")
    assert result["trade_type"] == "not-in-catalog"
    assert result["session_artifacts"]["extract"]["prompt_blob"] == "prompts/loan.txt"


def test_real_pdf_text_extraction():
    pdf = Path(__file__).parent / "fixtures/sample-loan-contract.pdf"
    text = extract_xml.pdf_to_text(pdf.read_bytes())
    assert isinstance(text, str) and len(text) > 100


def test_legacy_blob_paths_and_prompt_bytes(monkeypatch):
    monkeypatch.setattr(prompts, "_prompt_cache", {})
    read = MagicMock(return_value="prompt\r\nuntouched  \n")
    monkeypatch.setattr(prompts, "read_blob_text", read)
    config = {"storage": {"account_name": "company", "config_container": "agent-config"}}
    assert prompts.get_prompt_text(config, "prompts/loan.txt") == "prompt\r\nuntouched  \n"
    read.assert_called_once_with("company", "agent-config", "skills/intelligence-contract/prompts/loan.txt")


@pytest.mark.parametrize("resolver,debug", [
    ({"success": True, "trade_xml": "<trade><amount>10</amount></trade>", "warnings": ["", 1, None, "a"]}, False),
    ({"success": True, "trade_xml": " "}, True),
    ({"success": False, "trade_xml": "<trade/>", "message": "business failure", "warnings": "ignored"}, True),
    ({"success": True, "trade_xml": "malformed"}, False),
])
def test_full_result_matches_original(capture_runtime, monkeypatch, resolver, debug):
    import ast
    from typing import Any, Dict, List
    original_path = Path(__file__).resolve().parents[3] / "skills/intelligence_contract/run.py"
    if not original_path.is_file():
        pytest.skip("Original repository absent; standalone workflow tests still run")
    runtime = capture_runtime
    monkeypatch.setattr(workflow, "time", NS(perf_counter=lambda: 1.0))
    runtime.resolve.side_effect = None
    runtime.resolve.return_value = resolver
    namespace = {**vars(workflow), "intelligence_contract_config": prompts.capture_config,
                 "Any": Any, "Dict": Dict, "List": List}
    tree = ast.parse(original_path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(original_path), "exec"), namespace)
    kwargs = {"pdf_bytes": b"%PDF-test", "trade_type": "iamLoan", "cluster": runtime.cluster,
              "config": runtime.config, "azure": runtime.azure, "debug": debug}
    expected = asyncio.run(namespace["run_intelligence_contract"](**kwargs))
    actual = asyncio.run(workflow.run_capture(**kwargs))
    assert actual == expected


def test_original_catalog_refresh_name_collision_is_preserved(monkeypatch):
    # The original overwrites its _catalog_version function with the loaded version.
    # Characterize this existing defect without silently fixing refresh behavior.
    import importlib.util
    spec = importlib.util.spec_from_file_location("fresh_capture_prompts", Path(prompts.__file__))
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    monkeypatch.setattr(fresh, "read_blob_text", lambda *a: '{"version":"v1"}')
    cfg = {"storage": {"account_name": "company"}}
    assert fresh.init_capture_prompts(cfg)["version"] == "v1"
    with pytest.raises(TypeError, match="not callable"):
        fresh.refresh_capture_prompts(cfg)
