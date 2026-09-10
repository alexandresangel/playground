import unittest

from capture.workflow.xml_fields import count_extracted_fields


class CountExtractedFieldsTests(unittest.TestCase):
    def test_counts_populated_elements(self) -> None:
        xml = """
        <tradeMoneyMarket>
          <tradeType shortname="iamLoan">763</tradeType>
          <currency1 shortname="EUR">879</currency1>
          <amount1>2.2763E+7</amount1>
          <isFixed>false</isFixed>
        </tradeMoneyMarket>
        """.strip()
        self.assertEqual(count_extracted_fields(xml), 4)


if __name__ == "__main__":
    unittest.main()
