"""Deterministic field grading for trade XML; no network or model dependencies.

Rules are optional and reject unknown keys. ``include_fields``, ``ignore_fields``,
and ``critical_fields`` accept root-relative paths: ``amount1``,
``currency1/@shortname``, or ``@gracePeriod``. An element selector includes its
attributes and descendants. Repeated siblings use ``[1]``, ``[2]`` in reports;
an unindexed selector matches every occurrence. Include and critical selectors
must match populated ground truth. A critical field cannot be excluded/ignored.

``numeric_fields``, ``date_fields``, and ``boolean_fields`` add to the defaults
below. Normalization applies only to selected scalars, never arbitrary numeric
strings such as reference IDs. ``tolerances`` maps numeric paths to nonnegative
finite absolute decimal tolerances; all other numeric comparisons are exact.
Tolerance selectors must match populated ground truth. Dates/timestamps compare
as UTC instants, preserving clock times; date-only values mean midnight UTC and
timestamps without a timezone are assumed UTC. Reference/enum strings remain
case-sensitive.

``reference_mode`` defaults to ``shortname``: reference element text (typically
an internal ID) is ignored when a populated ``shortname`` or ``name`` attribute
exists. All such identifier attributes are still compared, as are any other
business attributes. ``strict`` additionally compares the element text.
Metadata attributes ``class`` and ``customDictionaryName`` are always ignored.
``fail_on_unexpected`` defaults to true; false permits additional fields but
still reports and includes them in precision. Empty values count as absent.

The root's namespace is implicit in paths; foreign namespaces retain Clark
notation. Root qualified names must match. DTD/entity declarations are rejected.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, InvalidOperation
import re
import xml.etree.ElementTree as ET


_NUMERIC = {"amount1", "amount2", "fixedRate", "spread"}
_DATES = {"tradeDate", "maturityDate", "firstCouponDate", "firstAmortizationDate"}
_BOOLEAN = {"isFixed"}
_METADATA = {"class", "customDictionaryName"}
_LIST_RULES = {"include_fields", "ignore_fields", "critical_fields", "numeric_fields", "date_fields", "boolean_fields"}
_RULE_KEYS = _LIST_RULES | {"tolerances", "reference_mode", "fail_on_unexpected"}


def _parse(xml: str, label: str) -> ET.Element:
    if not isinstance(xml, str) or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", xml, re.IGNORECASE):
        raise ValueError(f"Invalid {label} XML")
    try:
        return ET.fromstring(xml)
    except (ET.ParseError, ValueError, RecursionError):
        raise ValueError(f"Invalid {label} XML") from None


def _matches(selector: str, path: str, *, descendants: bool = True) -> bool:
    # Namespace URIs may contain slashes, so match the literal selector rather
    # than treating arbitrary path segments as independent XPath expressions.
    # Optional occurrence indices only follow unindexed element segments.
    parts = re.split(r"(/)(?![^{}]*\})", selector)
    expression = ""
    for part in parts:
        expression += re.escape(part)
        if part and part != "/" and not part.startswith("@") and not re.search(r"\[\d+\]$", part):
            expression += r"(?:\[\d+\])?"
    return re.match(r"^" + expression + (r"(?:/|$)" if descendants else "$"), path) is not None


def _any_match(selectors: list[str] | set[str], path: str, *, descendants: bool = True) -> bool:
    return any(_matches(selector, path, descendants=descendants) for selector in selectors)


def _validate_rules(rules: dict | None) -> dict:
    if rules is None:
        rules = {}
    if not isinstance(rules, dict) or set(rules) - _RULE_KEYS:
        raise ValueError("Invalid XML comparison rule keys")
    result = dict(rules)
    for key in _LIST_RULES:
        value = result.get(key, [])
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item or item != item.strip()
            or item.startswith("/") or item.endswith("/") or "//" in item.replace("http://", "").replace("https://", "")
            or "*" in item or ".." in item or re.search(r"\[(?![1-9]\d*\])", item)
            for item in value
        ):
            raise ValueError(f"Invalid {key} rule")
        if key == "include_fields" and key in result and not value:
            raise ValueError("include_fields must not be empty")
        result[key] = value
    mode = result.get("reference_mode", "shortname")
    if not isinstance(mode, str) or mode not in {"shortname", "strict"}:
        raise ValueError("Invalid reference_mode rule")
    if not isinstance(result.get("fail_on_unexpected", True), bool):
        raise ValueError("Invalid fail_on_unexpected rule")
    tolerances = result.get("tolerances", {})
    if not isinstance(tolerances, dict):
        raise ValueError("Invalid tolerances rule")
    parsed = {}
    for path, value in tolerances.items():
        if not isinstance(path, str) or not path or path != path.strip() or not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise ValueError("Invalid tolerances rule")
        try:
            decimal = Decimal(str(value))
        except InvalidOperation:
            raise ValueError("Invalid tolerances rule") from None
        if not decimal.is_finite() or decimal < 0:
            raise ValueError("Invalid tolerances rule")
        parsed[path] = decimal
    result["tolerances"] = parsed
    return result


def _flatten(root: ET.Element, namespace: str, reference_mode: str) -> tuple[dict, set]:
    """Use indexed internal paths; render indices only where either tree repeats."""
    values: dict[tuple[str, ...], str] = {}
    repeated: set[tuple[str, ...]] = set()

    def name(qualified: str) -> str:
        prefix = "{" + namespace + "}" if namespace else ""
        if prefix and qualified.startswith(prefix):
            return qualified[len(prefix):]
        # An explicitly unnamespaced child is different from one in the root's
        # namespace. XML default namespaces never apply to attributes.
        return "{}" + qualified if namespace and not qualified.startswith("{") else qualified

    def visit(element: ET.Element, path: tuple[str, ...]) -> None:
        for attribute, value in element.attrib.items():
            if attribute in _METADATA:
                continue
            if value.strip():
                values[path + ("@" + attribute,)] = value.strip()
        reference = reference_mode == "shortname" and any(element.get(key, "").strip() for key in ("shortname", "name"))
        if len(element) and element.text and element.text.strip():
            raise ValueError("Unsupported mixed XML content")
        if element.text and element.text.strip() and not reference:
            values[path or ("#text",)] = element.text.strip()
        # Mixed content is not a trade scalar and must not silently disappear.
        if any(child.tail and child.tail.strip() for child in element):
            raise ValueError("Unsupported mixed XML content")
        counts = Counter(child.tag for child in element)
        occurrences: Counter = Counter()
        for child in element:
            tag = name(child.tag)
            occurrences[child.tag] += 1
            if counts[child.tag] > 1:
                repeated.add(path + (tag,))
            visit(child, path + (f"{tag}[{occurrences[child.tag]}]",))

    visit(root, ())
    return values, repeated


def _render(values: dict, repeated: set) -> dict[str, str]:
    result = {}
    for path, value in values.items():
        parts = []
        for index, part in enumerate(path):
            plain = re.sub(r"\[\d+\]$", "", part)
            parts.append(part if path[:index] + (plain,) in repeated else plain)
        result["/".join(parts)] = value
    return result


def _kind(path: str, rules: dict) -> str:
    kinds = []
    for kind, defaults, rule in (("numeric", _NUMERIC, "numeric_fields"), ("date", _DATES, "date_fields"), ("boolean", _BOOLEAN, "boolean_fields")):
        if _any_match(defaults | set(rules[rule]), path, descendants=False):
            kinds.append(kind)
    if len(kinds) > 1:
        raise ValueError("Conflicting scalar normalization rules")
    return kinds[0] if kinds else "text"


def _normalize(value: str, kind: str):
    if kind == "numeric":
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise ValueError("Invalid numeric field") from None
        if not number.is_finite():
            raise ValueError("Invalid numeric field")
        return number
    if kind == "date":
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]", value):
                raise ValueError
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise ValueError("Invalid date field") from None
    if kind == "boolean":
        if value in {"true", "1"}:
            return True
        if value in {"false", "0"}:
            return False
        raise ValueError("Invalid boolean field")
    return value


def compare_xml(expected_xml: str, actual_xml: str, *, rules: dict | None = None) -> dict:
    """Return JSON-safe field outcomes, counts, precision, recall, and pass flags.

    Invalid ground truth, malformed XML, incompatible roots, or contradictory
    rules raise ValueError. Invalid actual scalar values grade as incorrect.
    With no populated expected fields the comparison cannot pass; undefined
    precision/recall are ``None``, so absence cannot inflate reported accuracy.
    """
    config = _validate_rules(rules)
    expected_root, actual_root = _parse(expected_xml, "expected"), _parse(actual_xml, "actual")
    if expected_root.tag != actual_root.tag:
        raise ValueError("XML root names do not match")
    namespace = expected_root.tag[1:].split("}", 1)[0] if expected_root.tag.startswith("{") else ""
    mode = config.get("reference_mode", "shortname")
    expected_values, expected_repeated = _flatten(expected_root, namespace, mode)
    actual_values, actual_repeated = _flatten(actual_root, namespace, mode)
    repeated = expected_repeated | actual_repeated
    expected, actual = _render(expected_values, repeated), _render(actual_values, repeated)
    include, ignore, critical = (config[key] for key in ("include_fields", "ignore_fields", "critical_fields"))
    for selector in include + critical:
        if not any(_matches(selector, path) for path in expected):
            raise ValueError("Include or critical selector matches no populated expected field")

    def selected(path: str) -> bool:
        return (not include or _any_match(include, path)) and not _any_match(ignore, path)

    if any(_any_match(critical, path) and not selected(path) for path in expected):
        raise ValueError("Critical fields cannot be excluded or ignored")
    expected = {path: value for path, value in expected.items() if selected(path)}
    actual = {path: value for path, value in actual.items() if selected(path)}
    if include and not expected:
        raise ValueError("No populated expected fields remain for comparison")
    paths = set(expected) | set(actual)
    kinds = {path: _kind(path, config) for path in paths}
    for selector in config["tolerances"]:
        if not any(_matches(selector, path, descendants=False) for path in expected):
            raise ValueError("Tolerance selector matches no populated expected field")
    tolerances = {}
    for path in paths:
        matching = [value for selector, value in config["tolerances"].items() if _matches(selector, path, descendants=False)]
        if matching and (kinds[path] != "numeric" or len(set(matching)) > 1):
            raise ValueError("Conflicting or nonnumeric tolerance rule")
        tolerances[path] = matching[0] if matching else Decimal(0)
    fields = []
    counts = {"correct": 0, "missing": 0, "incorrect": 0, "unexpected": 0, "expected": len(expected), "predicted": len(actual)}
    for path in sorted(paths):
        gold, prediction = expected.get(path), actual.get(path)
        normalized = _normalize(gold, kinds[path]) if gold is not None else None
        if gold is None:
            status = "unexpected"
        elif prediction is None:
            status = "missing"
        else:
            try:
                candidate = _normalize(prediction, kinds[path])
                equal = abs(normalized - candidate) <= tolerances[path] if kinds[path] == "numeric" else normalized == candidate
            except (ValueError, DecimalException):
                equal = False
            status = "correct" if equal else "incorrect"
        counts[status] += 1
        fields.append({"path": path, "expected": gold, "actual": prediction, "status": status, "critical": _any_match(critical, path)})
    critical_pass = all(field["status"] == "correct" for field in fields if field["critical"])
    passed = bool(expected) and critical_pass and not counts["missing"] and not counts["incorrect"] and (not config.get("fail_on_unexpected", True) or not counts["unexpected"])
    return {"fields": fields, "counts": counts,
            "precision": counts["correct"] / counts["predicted"] if counts["predicted"] else None,
            "recall": counts["correct"] / counts["expected"] if counts["expected"] else None,
            "critical_pass": critical_pass, "passed": passed}
