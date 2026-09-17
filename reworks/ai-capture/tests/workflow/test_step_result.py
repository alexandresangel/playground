"""Public workflow output, resolver failures, warnings, debug and timings."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_result_uses_resolved_xml_and_counts_its_fields(workflow):
    workflow.resolver.return_value = {
        "success": True,
        "trade_xml": "  <trade><amount>99</amount></trade>\n",
    }
    result = await workflow.run()
    assert result["trade_xml"] == "<trade><amount>99</amount></trade>"
    assert result["extracted_field_count"] == 1
    assert result["message"] == ""
    assert result["warnings"] == []
    assert set(result) == {
        "success",
        "trade_xml",
        "view_entity",
        "menu_name",
        "trade_type",
        "extracted_field_count",
        "message",
        "warnings",
        "tool_trace",
        "timings_ms",
    }
    for stage, entry in zip(("extract", "resolve"), result["tool_trace"]):
        duration = result["timings_ms"][stage]
        assert isinstance(duration, int) and duration >= 0
        assert entry["duration_ms"] == duration


@pytest.mark.parametrize(
    "body,message",
    [
        pytest.param(
            {"success": True},
            "resolveReferences returned success but no trade_xml",
            id="missing-xml",
        ),
        pytest.param(
            {"success": True, "trade_xml": " \n"},
            "resolveReferences returned success but no trade_xml",
            id="blank-xml",
        ),
        pytest.param(
            {"success": True, "message": "server explanation"},
            "server explanation",
            id="preserve-server-message",
        ),
        pytest.param(
            {
                "success": False,
                "message": "unresolved",
                "trade_xml": "<trade><amount>1</amount></trade>",
            },
            "unresolved",
            id="failed-with-xml",
        ),
        pytest.param({}, "", id="missing-success"),
    ],
)
async def test_unsuccessful_resolution_returns_failure_and_zero_fields(workflow, body, message):
    workflow.resolver.return_value = body
    result = await workflow.run()
    assert result["success"] is False
    assert result["extracted_field_count"] == 0
    assert result["message"] == message
    assert len(result["tool_trace"]) == 2
    assert "debug" not in result


@pytest.mark.parametrize(
    "warnings,expected",
    [
        (["review", None, "", 0, 7], ["review", "7"]),
        ("single warning", []),
        (None, []),
        ({"message": "warning"}, []),
    ],
)
async def test_only_warning_lists_are_exposed_as_nonempty_strings(workflow, warnings, expected):
    workflow.resolver.return_value["warnings"] = warnings
    assert (await workflow.run())["warnings"] == expected


@pytest.mark.parametrize("debug", [False, True])
async def test_debug_details_are_explicitly_opt_in_even_on_failure(workflow, debug):
    workflow.resolver.return_value = {"success": False, "message": "unresolved"}
    result = await workflow.run(debug=debug)
    assert ("debug" in result) is debug
    if debug:
        assert result["debug"]["resolve_references"] == workflow.resolver.return_value
        assert result["debug"]["extract"]["pdf_text_length"] > 0
        assert result["debug"]["resolve_references_request"] == workflow.resolver.call_args.args[2]
