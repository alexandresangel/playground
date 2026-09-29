import pytest

from evals.xml_compare import compare_xml


def xml(content="", attrs=""):
    return f"<tradeMoneyMarket{attrs}>{content}</tradeMoneyMarket>"


def test_decimal_dates_and_boolean_are_normalized_explicitly():
    expected = xml("<amount1>1000000.00</amount1><fixedRate>3.5</fixedRate><tradeDate>2026-01-02</tradeDate><isFixed>true</isFixed>")
    actual = xml("<isFixed>1</isFixed><amount1>1e6</amount1><fixedRate>3.500</fixedRate><tradeDate>2026-01-02T00:00:00.000Z</tradeDate>")
    result = compare_xml(expected, actual)
    assert result["passed"]
    assert result["counts"]["correct"] == 4
    assert result["precision"] == result["recall"] == 1


@pytest.mark.parametrize("actual, correct", [
    ("2026-01-02T00:00:00.000Z", True),
    ("2026-01-02T00:00:00", True),
    ("2026-01-02T01:00:00+01:00", True),
    ("2026-01-02T23:00:00Z", False),
    ("2026-01-02T02:00:00+03:00", False),
    ("2026-01-03T00:00:00Z", False),
])
def test_dates_preserve_time_and_compare_utc_instants(actual, correct):
    result = compare_xml(xml("<tradeDate>2026-01-02</tradeDate>"), xml(f"<tradeDate>{actual}</tradeDate>"))
    assert result["passed"] is correct


def test_exact_rates_and_opt_in_absolute_tolerance():
    expected, actual = xml("<fixedRate>3.5</fixedRate>"), xml("<fixedRate>3.50001</fixedRate>")
    assert not compare_xml(expected, actual)["passed"]
    assert compare_xml(expected, actual, rules={"tolerances": {"fixedRate": "0.00001"}})["passed"]


def test_reference_identifiers_are_exact_and_ids_optional():
    gold = xml('<cpty name="Bank A" class="Entity">12</cpty><currency1 shortname="EUR"/>')
    actual = xml('<currency1 shortname="EUR"/><cpty name="Bank A" class="Other">999</cpty>')
    assert compare_xml(gold, actual)["passed"]
    assert not compare_xml(gold, actual, rules={"reference_mode": "strict"})["passed"]
    wrong_party = actual.replace("Bank A", "Bank B")
    result = compare_xml(gold, wrong_party, rules={"critical_fields": ["cpty"]})
    assert not result["critical_pass"]
    assert next(field for field in result["fields"] if field["path"] == "cpty/@name")["status"] == "incorrect"


def test_nonmetadata_attributes_are_scored_and_dictionary_metadata_is_ignored():
    expected = xml('<frequency shortname="3M" customDictionaryName="frequency" type="coupon"/>')
    actual = xml('<frequency shortname="3M" customDictionaryName="changed" type="principal"/>')
    result = compare_xml(expected, actual)
    assert result["counts"]["incorrect"] == 1
    assert result["counts"]["expected"] == 2


def test_numeric_field_normalization_does_not_apply_to_its_attributes():
    value = xml('<amount1 unit="EUR">1</amount1>')
    assert compare_xml(value, value)["passed"]


def test_counts_missing_unexpected_empty_and_zero():
    result = compare_xml(xml("<amount1>0</amount1><spread/><fixedRate>2</fixedRate>"), xml("<amount1/><spread>0</spread><fixedRate>3</fixedRate>"))
    assert result["counts"] == {"correct": 0, "missing": 1, "incorrect": 1, "unexpected": 1, "expected": 2, "predicted": 2}
    assert result["precision"] == result["recall"] == 0
    empty = compare_xml(xml("<amount1/>"), xml())
    assert empty["precision"] is empty["recall"] is None
    assert not empty["passed"]


def test_unexpected_fields_still_reported_when_allowed():
    result = compare_xml(xml("<amount1>1</amount1>"), xml("<amount1>1</amount1><spread>9</spread>"), rules={"fail_on_unexpected": False})
    assert result["passed"]
    assert result["precision"] == 0.5
    assert result["counts"]["unexpected"] == 1


def test_root_attributes_are_graded():
    result = compare_xml(xml(attrs=' gracePeriod="2" interestGracePeriod="3"'), xml(attrs=' gracePeriod="3" interestGracePeriod="3"'), rules={"critical_fields": ["@gracePeriod"]})
    assert result["counts"]["incorrect"] == 1
    assert not result["critical_pass"]


def test_repeated_siblings_preserve_occurrences_and_align_singleton():
    result = compare_xml(xml("<amount1>1</amount1>"), xml("<amount1>1</amount1><amount1>2</amount1>"))
    assert [(field["path"], field["status"]) for field in result["fields"]] == [("amount1[1]", "correct"), ("amount1[2]", "unexpected")]
    repeated = xml("<schedule><payment><amount>1</amount></payment><payment><amount>2</amount></payment></schedule>")
    result = compare_xml(repeated, repeated.replace("<amount>2</amount>", "<amount>3</amount>"), rules={"critical_fields": ["schedule/payment/amount"]})
    assert result["counts"]["incorrect"] == 1
    assert not result["critical_pass"]


def test_include_ignore_and_critical_paths():
    expected = xml('<amount1>1</amount1><cpty name="A"/>')
    result = compare_xml(expected, xml('<cpty name="A"/>'), rules={"include_fields": ["cpty"], "critical_fields": ["cpty"]})
    assert result["passed"]
    assert result["counts"]["expected"] == 1
    result = compare_xml(expected, xml(), rules={"critical_fields": ["amount1"]})
    assert result["counts"]["missing"] == 2
    assert not result["critical_pass"]


@pytest.mark.parametrize("rules", [
    {"unknown": True}, {"include_fields": []}, {"include_fields": ["typo"]},
    {"critical_fields": ["typo"]}, {"critical_fields": ["amount1"], "ignore_fields": ["amount1"]},
    {"critical_fields": ["amount1"], "include_fields": ["isFixed"]},
    {"numeric_fields": ["isFixed"]}, {"tolerances": {"amount1": "-1"}},
    {"tolerances": {"amountl": "1"}}, {"tolerances": {"amount1/@unit": "0"}},
    {"tolerances": {"amount1": "NaN"}}, {"tolerances": {"isFixed": "0"}},
    {"reference_mode": "fuzzy"}, {"reference_mode": []}, {"fail_on_unexpected": "false"},
])
def test_invalid_or_conflicting_rules_fail(rules):
    value = xml("<amount1>1</amount1><isFixed>true</isFixed>")
    with pytest.raises(ValueError):
        compare_xml(value, value, rules=rules)


def test_custom_normalization_does_not_change_reference_or_enum_strings():
    assert not compare_xml(xml('<currency1 shortname="eur"/>'), xml('<currency1 shortname="EUR"/>'))["passed"]
    assert not compare_xml(xml("<code>01</code>"), xml("<code>1</code>"))["passed"]
    assert compare_xml(xml("<customAmount>01</customAmount>"), xml("<customAmount>1</customAmount>"), rules={"numeric_fields": ["customAmount"]})["passed"]


def test_invalid_actual_scalar_is_a_failure_not_a_crash():
    result = compare_xml(xml("<amount1>1</amount1><tradeDate>2026-01-01</tradeDate><isFixed>true</isFixed>"), xml("<amount1>NaN</amount1><tradeDate>nonsense</tradeDate><isFixed>yes</isFixed>"))
    assert result["counts"]["incorrect"] == 3


def test_namespaces_are_preserved_and_root_namespace_is_implicit_in_paths():
    expected = '<tradeMoneyMarket xmlns="urn:trade"><amount1>1</amount1></tradeMoneyMarket>'
    actual = '<t:tradeMoneyMarket xmlns:t="urn:trade"><t:amount1>1.0</t:amount1></t:tradeMoneyMarket>'
    assert compare_xml(expected, actual, rules={"critical_fields": ["amount1"]})["passed"]
    with pytest.raises(ValueError, match="root"):
        compare_xml(expected, actual.replace("urn:trade", "urn:other"))
    unnamespaced_child = '<tradeMoneyMarket xmlns="urn:trade"><amount1 xmlns="">1</amount1></tradeMoneyMarket>'
    result = compare_xml(expected, unnamespaced_child)
    assert result["counts"]["missing"] == result["counts"]["unexpected"] == 1


@pytest.mark.parametrize("bad", ["<", "<secret>", '<!DOCTYPE t [<!ENTITY x "private">]><tradeMoneyMarket>&x;</tradeMoneyMarket>'])
def test_malformed_xml_and_dtd_rejected_without_echoing_data(bad):
    with pytest.raises(ValueError, match="^Invalid actual XML$"):
        compare_xml(xml("<amount1>1</amount1>"), bad)


def test_root_mismatch_and_mixed_content_rejected():
    with pytest.raises(ValueError, match="root"):
        compare_xml(xml(), "<error/>")
    with pytest.raises(ValueError, match="mixed"):
        compare_xml(xml("<amount1>1</amount1>"), xml("<amount1>1</amount1>discarded"))
