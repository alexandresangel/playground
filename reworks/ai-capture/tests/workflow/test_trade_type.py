"""The caller, not the model, selects Capture's trade type."""

import xml.etree.ElementTree as ET

import pytest

from capture.workflow.extract_xml import apply_trade_type_shortname


def test_replaces_existing_trade_type() -> None:
    xml = '<tradeMoneyMarket><tradeType shortname="mltLoan"/></tradeMoneyMarket>'
    updated = apply_trade_type_shortname(xml, "iamLoan")
    assert 'shortname="iamLoan"' in updated
    assert 'shortname="mltLoan"' not in updated


def test_adds_trade_type_when_missing() -> None:
    xml = "<tradeMoneyMarket><entity name='X'/></tradeMoneyMarket>"
    updated = apply_trade_type_shortname(xml, "iamLoan")
    assert 'shortname="iamLoan"' in updated


@pytest.mark.parametrize(
    "xml",
    [
        '<trade><tradeType shortname="wrong">model-id</tradeType><amount>123</amount></trade>',
        '<trade xmlns="urn:trade"><tradeType shortname="wrong">model-id</tradeType><amount>123</amount></trade>',
        '<trade><TRADETYPE shortname="wrong">model-id</TRADETYPE><amount>123</amount></trade>',
    ],
)
def test_enforcement_handles_namespaces_and_clears_model_identifier(xml):
    root = ET.fromstring(apply_trade_type_shortname(xml, " iamLoan "))
    fields = list(root)
    assert fields[0].get("shortname") == "iamLoan"
    assert fields[0].text is None
    assert fields[1].text == "123"


@pytest.mark.parametrize("trade_type", [None, "", "  "])
def test_empty_trade_type_is_rejected(trade_type):
    with pytest.raises(ValueError, match="trade_type is required"):
        apply_trade_type_shortname("<trade/>", trade_type)


def test_malformed_xml_is_rejected():
    with pytest.raises(ValueError, match="Invalid trade XML"):
        apply_trade_type_shortname("<trade>", "iamLoan")
