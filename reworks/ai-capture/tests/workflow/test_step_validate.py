"""Validation stops invalid inputs before catalog, model, or resolver work."""

from unittest.mock import Mock

import pytest

from capture.workflow import graph, prompts
from capture.workflow.extract_xml import validate_pdf_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pdf,error",
    [
        pytest.param(b"", "empty", id="empty-upload"),
        pytest.param(b"not pdf", "not a PDF", id="missing-pdf-header"),
        pytest.param(b"%PDF-" + b"x" * 50, "max size", id="over-size-limit"),
    ],
)
async def test_invalid_pdf_stops_before_catalog_and_external_calls(
    workflow, pdf, error, monkeypatch
):
    workflow.config["capture"]["max_pdf_bytes"] = 20
    lookup = Mock(side_effect=AssertionError("catalog must not be read"))
    monkeypatch.setattr(graph, "get_trade_type_config", lookup)
    with pytest.raises(ValueError, match=error):
        await workflow.run(pdf_bytes=pdf)
    lookup.assert_not_called()
    workflow.completion.assert_not_called()
    workflow.resolver.assert_not_called()


def test_pdf_at_exact_byte_limit_is_accepted():
    validate_pdf_bytes(b"%PDF-test", max_bytes=9)
    with pytest.raises(ValueError, match="max size"):
        validate_pdf_bytes(b"%PDF-test!", max_bytes=9)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "trade_type,error", [("  ", "required"), ("unknown", "Unknown trade_type")]
)
async def test_invalid_trade_type_stops_before_model_and_resolver(
    workflow, monkeypatch, trade_type, error
):
    monkeypatch.setattr(prompts, "_catalog", {"prompts": {"prompt.txt": ["known"]}})
    with pytest.raises(ValueError, match=error):
        await workflow.run(trade_type=trade_type)
    workflow.completion.assert_not_called()
    workflow.resolver.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "catalog,config,expected",
    [
        pytest.param(
            {"view_entity": "commercialPaper", "menu_name": "paperMenu"},
            {"view_entity": "fallback"},
            ("commercialPaper", "paperMenu"),
            id="catalog-over-config",
        ),
        pytest.param(
            {}, {"view_entity": "configured"}, ("configured", "configured"), id="config-fallback"
        ),
        pytest.param({}, {}, ("loanDeposit", "loanDeposit"), id="built-in-fallback"),
    ],
)
async def test_view_and_menu_selection_reaches_resolver(
    workflow, monkeypatch, catalog, config, expected
):
    monkeypatch.setattr(
        prompts, "_catalog", {"prompts": {"prompts/mltLoan.txt": {"types": ["iamLoan"], **catalog}}}
    )
    workflow.config = {"capture": config}
    result = await workflow.run()
    assert (result["view_entity"], result["menu_name"]) == expected
    assert workflow.resolver.call_args.args[2]["view_entity"] == expected[0]
