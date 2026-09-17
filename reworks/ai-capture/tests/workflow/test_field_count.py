"""Count populated resolved fields without counting root or duplicate values."""

import pytest

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


@pytest.mark.parametrize(
    "xml,expected",
    [
        (None, 0),
        ("", 0),
        ("  ", 0),
        ("<broken", 0),
        ("<trade/>", 0),
        ('<trade name="root">root text<empty/> <blank>  </blank></trade>', 0),
        ('<trade><entity shortname="E" name="Entity">123</entity></trade>', 1),
        ('<trade><entity name="Entity"/><amount>0</amount><fixed>false</fixed></trade>', 3),
        (
            '<trade><entity shortname=" " name="Entity"/><group><amount>12</amount></group></trade>',
            2,
        ),
        ('<trade xmlns="urn:trade"><amount>12</amount></trade>', 1),
    ],
)
def test_counting_boundaries(xml, expected):
    assert count_extracted_fields(xml) == expected
