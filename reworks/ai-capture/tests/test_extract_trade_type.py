"""Unit tests for trade_type enforcement in IC extract XML."""

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