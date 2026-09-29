"""Versioned PDF / reviewed XML datasets, validated before any API request."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from evals.xml_compare import compare_xml


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Case:
    id: str
    pdf: Path
    trade_type: str
    expected: dict[str, str]
    rules: dict[str, dict]
    split: str
    tags: tuple[str, ...]
    expected_status: int
    expected_success: bool
    identity: dict


@dataclass(frozen=True)
class Dataset:
    name: str
    version: str
    fingerprint: str
    cases: tuple[Case, ...]
    manifest: dict


def _object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def _keys(value: dict, allowed: set[str], label: str) -> None:
    if value.keys() - allowed:
        raise ValueError(f"{label} contains unknown keys")


def load_dataset(path: Path) -> Dataset:
    path = path.resolve()
    try:
        raw = path.read_bytes()
        data = _object(json.loads(raw), "Dataset")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Cannot read dataset JSON") from None
    _keys(data, {"schema_version", "name", "version", "description", "rules", "cases"}, "Dataset")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Dataset schema_version must be 1")
    name, version = _text(data.get("name"), "Dataset name"), _text(data.get("version"), "Dataset version")
    defaults = _object(data.get("rules", {}), "Dataset rules")
    rows = data.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Dataset cases must be a nonempty list")
    cases, ids = [], set()
    for row in rows:
        row = _object(row, "Case")
        _keys(row, {"id", "pdf", "trade_type", "expected_xml", "expected_extracted_xml", "rules",
                    "extracted_rules", "split", "tags", "expected_status", "expected_success",
                    "reviewer", "notes"}, "Case")
        case_id = _text(row.get("id"), "Case id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", case_id):
            raise ValueError("Case id must contain only letters, numbers, underscore or hyphen")
        # Portable artifact paths: avoid case collisions and Windows device names.
        if case_id.casefold() in ids or re.fullmatch(r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])", case_id):
            raise ValueError("Duplicate or reserved case id")
        ids.add(case_id.casefold())
        trade_type = _text(row.get("trade_type"), f"{case_id}: trade_type")
        pdf = (path.parent / _text(row.get("pdf"), f"{case_id}: pdf")).resolve()
        try:
            pdf_bytes = pdf.read_bytes()
        except OSError:
            raise ValueError(f"{case_id}: cannot read PDF") from None
        status = row.get("expected_status", 200)
        success = row.get("expected_success", True)
        if type(status) is not int or not 100 <= status <= 599 or type(success) is not bool:
            raise ValueError(f"{case_id}: invalid expected_status or expected_success")
        if success and status != 200:
            raise ValueError(f"{case_id}: successful extraction requires expected_status 200")
        if not success and "expected_status" not in row:
            raise ValueError(f"{case_id}: negative cases require explicit expected_status")
        if success and not pdf_bytes.startswith(b"%PDF-"):
            raise ValueError(f"{case_id}: input does not have a PDF header")
        split = _text(row.get("split", "dev"), f"{case_id}: split")
        tags = row.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(t, str) or not t.strip() for t in tags):
            raise ValueError(f"{case_id}: tags must be nonempty strings")
        expected, rules, hashes = {}, {}, {}
        case_rules = {**defaults, **_object(row.get("rules", {}), f"{case_id}: rules")}
        for stage, key in (("resolved", "expected_xml"), ("extracted", "expected_extracted_xml")):
            if key not in row:
                continue
            reference = (path.parent / _text(row[key], f"{case_id}: {key}")).resolve()
            try:
                content = reference.read_bytes()
                expected[stage] = content.decode("utf-8-sig")
            except (OSError, UnicodeDecodeError):
                raise ValueError(f"{case_id}: cannot read {key}") from None
            rules[stage] = case_rules if stage == "resolved" else {
                **case_rules, **_object(row.get("extracted_rules", {}), f"{case_id}: extracted_rules")}
            # Validate labels, selectors and rules up front, before spending any model tokens.
            check = compare_xml(expected[stage], expected[stage], rules=rules[stage])
            if not check["passed"] or not check["counts"]["expected"]:
                raise ValueError(f"{case_id}: {key} must contain scorable expected fields")
            hashes[stage] = sha256(content)
        if success and "resolved" not in expected:
            raise ValueError(f"{case_id}: expected_xml is required for successful cases")
        if not success and expected:
            raise ValueError(f"{case_id}: negative cases must not have ground-truth XML")
        identity = {"id": case_id, "trade_type": trade_type, "pdf_sha256": sha256(pdf_bytes),
                    "expected_sha256": hashes, "rules": rules, "expected_status": status,
                    "expected_success": success, "split": split, "tags": tags}
        cases.append(Case(case_id, pdf, trade_type, expected, rules, split, tuple(tags), status, success, identity))
    fingerprint = sha256(json.dumps({"name": name, "version": version, "cases": [c.identity for c in cases]},
                                    sort_keys=True, separators=(",", ":")).encode())
    return Dataset(name, version, fingerprint, tuple(cases), data)


def select_cases(dataset: Dataset, *, split: str | None = None, tags: list[str] | None = None) -> tuple[Case, ...]:
    selected = tuple(c for c in dataset.cases if (split is None or c.split == split)
                     and (not tags or set(tags) <= set(c.tags)))
    if not selected:
        raise ValueError("No dataset cases match the selection")
    return selected
