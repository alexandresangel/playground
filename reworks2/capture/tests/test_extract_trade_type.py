"""Unit tests for trade_type enforcement in IC extract XML."""

import unittest

from capture.workflow.extract_xml import apply_trade_type_shortname


class ApplyTradeTypeShortnameTests(unittest.TestCase):
    def test_replaces_existing_trade_type(self) -> None:
        xml = '<tradeMoneyMarket><tradeType shortname="mltLoan"/></tradeMoneyMarket>'
        updated = apply_trade_type_shortname(xml, "iamLoan")
        self.assertIn('shortname="iamLoan"', updated)
        self.assertNotIn('shortname="mltLoan"', updated)

    def test_adds_trade_type_when_missing(self) -> None:
        xml = "<tradeMoneyMarket><entity name='X'/></tradeMoneyMarket>"
        updated = apply_trade_type_shortname(xml, "iamLoan")
        self.assertIn('shortname="iamLoan"', updated)


if __name__ == "__main__":
    unittest.main()
