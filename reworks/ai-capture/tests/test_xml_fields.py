from capture.workflow.xml_fields import count_extracted_fields


def test_counts_populated_elements() -> None:
    xml = """
    <tradeMoneyMarket>
        <tradeType shortname="iamLoan">763</tradeType>
        <currency1 shortname="EUR">879</currency1>
        <amount1>2.2763E+7</amount1>
        <isFixed>false</isFixed>
    </tradeMoneyMarket>
    """.strip()
    assert count_extracted_fields(xml) == 4