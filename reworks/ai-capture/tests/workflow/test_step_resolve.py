"""Resolution receives enforced XML and propagates remote failures."""

import xml.etree.ElementTree as ET

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "trade_type,view_entity,menu_name",
    [
        ("iamLoan", "loanDeposit", "loanDeposit"),
        ("buyDiscountedPaper", "commercialPaper", "commercialPaper"),
        ("commercialLease", "loanDeposit", "commercialLease"),
    ],
)
async def test_resolver_receives_only_view_and_enforced_xml(
    workflow, trade_type, view_entity, menu_name
):
    result = await workflow.run(trade_type=trade_type)
    args, kwargs = workflow.resolver.call_args
    assert args[:2] == (workflow.cluster.diapason, "resolveReferences")
    assert set(args[2]) == {"view_entity", "trade_xml"}
    assert args[2]["view_entity"] == view_entity
    assert ET.fromstring(args[2]["trade_xml"]).find("tradeType").get("shortname") == trade_type
    assert kwargs == {"timeout_s": 180.0}
    trace = result["tool_trace"][1]
    assert trace["mcp_server"] == "default"
    assert trace["mcp_label"] == "Diapason"
    assert trace["arguments"] == {
        "view_entity": view_entity,
        "menu_name": menu_name,
        "trade_type": trade_type,
    }


async def test_resolver_error_aborts_graph_without_retry_or_partial_result(workflow):
    workflow.resolver.side_effect = RuntimeError("resolver unavailable")
    with pytest.raises(RuntimeError, match="resolver unavailable"):
        await workflow.run()
    workflow.completion.assert_called_once()
    workflow.resolver.assert_called_once()
