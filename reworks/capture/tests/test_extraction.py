import pytest

from capture.extraction import (
    apply_trade_type_shortname,
    count_extracted_fields,
    extract_xml_from_llm,
    validate_pdf_bytes,
)


def test_validate_pdf_requires_magic_header() -> None:
    with pytest.raises(ValueError, match="not a PDF"):
        validate_pdf_bytes(b"not-pdf", max_bytes=100)


def test_validate_pdf_enforces_limit() -> None:
    with pytest.raises(ValueError, match="max size"):
        validate_pdf_bytes(b"%PDF-" + b"x" * 20, max_bytes=10)


def test_trade_type_is_forced_from_caller() -> None:
    source = '<tradeMoneyMarket><tradeType shortname="wrong"/></tradeMoneyMarket>'
    result = apply_trade_type_shortname(source, "iamLoan")
    assert 'shortname="iamLoan"' in result
    assert "wrong" not in result


def test_extract_xml_keeps_legacy_fence_behavior() -> None:
    assert extract_xml_from_llm("before```xml\n<trade/>\n```after") == "<trade/>"


def test_count_extracted_fields_matches_legacy_rules() -> None:
    xml = '<trade><entity name="ACME"/><currency shortname="EUR"/><amount>12</amount></trade>'
    assert count_extracted_fields(xml) == 3
