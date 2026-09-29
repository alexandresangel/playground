"""Run live captures explicitly, or grade saved responses entirely offline."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import statistics
from typing import Any, Callable
import xml.etree.ElementTree as ET

from evals.dataset import Case, Dataset, select_cases, sha256
from evals.xml_compare import compare_xml


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _empty_reference(xml: str) -> str:
    return ET.tostring(ET.Element(ET.fromstring(xml).tag), encoding="unicode")


def grade_case(case: Case, capture: dict, *, attempt: int, artifacts: str) -> dict:
    response = capture.get("response")
    body = response if isinstance(response, dict) else {}
    debug = body.get("debug") if isinstance(body.get("debug"), dict) else {}
    extract = debug.get("extract") if isinstance(debug.get("extract"), dict) else {}
    source = debug.get("resolve_references_request")
    source = source if isinstance(source, dict) else {}
    actual = {"resolved": body.get("trade_xml"), "extracted": extract.get("trade_xml") or source.get("trade_xml")}
    # HTTP error responses commonly have no `success`; an absent status (transport error) never passes.
    status = capture.get("status_code")
    business_success = body.get("success") is True
    behavior_pass = status == case.expected_status and business_success == case.expected_success
    if capture.get("artifact_error"):
        behavior_pass = False
    if "pdf_sha256" in capture and (capture["pdf_sha256"] != case.identity["pdf_sha256"] or capture.get("trade_type") != case.trade_type):
        behavior_pass = False
    if case.expected_success:
        behavior_pass = behavior_pass and capture.get("success") is True
    elif status == 200:
        behavior_pass = behavior_pass and body.get("success") is False
    stages = {}
    for stage, expected in case.expected.items():
        xml = actual[stage]
        error = None
        if not isinstance(xml, str) or not xml.strip():
            xml, error = _empty_reference(expected), "missing_xml"
        try:
            comparison = compare_xml(expected, xml, rules=case.rules[stage])
        except ValueError:
            # Keep failed attempts in recall denominators; never silently drop malformed outputs.
            comparison = compare_xml(expected, _empty_reference(expected), rules=case.rules[stage])
            error = "invalid_xml"
        if error:
            comparison["passed"] = False
            comparison["error"] = error
        stages[stage] = comparison
    return {"case_id": case.id, "attempt": attempt, "trade_type": case.trade_type,
            "split": case.split, "tags": list(case.tags), "artifacts": artifacts,
            "status_code": status, "expected_status": case.expected_status,
            "expected_success": case.expected_success, "behavior_pass": behavior_pass,
            "capture_error": capture.get("error_category") or capture.get("error"),
            "input_verified": capture.get("pdf_sha256") == case.identity["pdf_sha256"] and capture.get("trade_type") == case.trade_type,
            "duration_seconds": capture.get("duration_seconds"),
            "passed": bool(behavior_pass and all(s["passed"] for s in stages.values())), "stages": stages}


def _summarize(records: list[dict]) -> dict:
    by_case: dict[str, list[bool]] = {}
    stages = {}
    for record in records:
        by_case.setdefault(record["case_id"], []).append(record["passed"])
        for stage, result in record["stages"].items():
            bucket = stages.setdefault(stage, {"counts": {k: 0 for k in ("correct", "missing", "incorrect", "unexpected", "expected", "predicted")},
                                               "attempts": 0, "passed": 0, "critical_failures": 0})
            bucket["attempts"] += 1
            bucket["passed"] += int(result["passed"])
            bucket["critical_failures"] += int(not result["critical_pass"])
            for key in bucket["counts"]:
                bucket["counts"][key] += result["counts"][key]
    for bucket in stages.values():
        counts = bucket["counts"]
        bucket["precision"] = counts["correct"] / counts["predicted"] if counts["predicted"] else None
        bucket["recall"] = counts["correct"] / counts["expected"] if counts["expected"] else None
    durations = [r["duration_seconds"] for r in records if isinstance(r.get("duration_seconds"), (int, float))]
    return {"attempts": len(records), "passed_attempts": sum(r["passed"] for r in records),
            "cases": len(by_case), "consistently_passing_cases": sum(all(v) for v in by_case.values()),
            "unstable_cases": [k for k, v in by_case.items() if any(v) and not all(v)],
            "behavior_failures": sum(not r["behavior_pass"] for r in records),
            "unverified_input_attempts": sum(not r["input_verified"] for r in records),
            "median_duration_seconds": statistics.median(durations) if durations else None, "stages": stages}


def compare_baseline(report: dict, baseline: dict) -> dict:
    if baseline.get("schema_version") != 1 or baseline.get("dataset", {}).get("fingerprint") != report["dataset"]["fingerprint"]:
        raise ValueError("Baseline uses a different dataset, ground truth or grading rules")
    if sorted(baseline.get("selected_cases", [])) != sorted(report["selected_cases"]):
        raise ValueError("Baseline case selection differs")
    for value in (report, baseline):
        if value.get("complete") is not True or not value.get("records"):
            raise ValueError("Baseline comparison requires complete nonempty reports")
        if {r["case_id"] for r in value["records"]} != set(value["selected_cases"]):
            raise ValueError("Baseline comparison requires records for every selected case")
    coverage = lambda value: sorted((r["case_id"], r["attempt"], sorted(r["stages"])) for r in value["records"])
    if coverage(report) != coverage(baseline):
        raise ValueError("Baseline attempts or stages differ")
    def outcomes(value: dict) -> dict:
        result: dict[tuple, list[bool]] = {}
        for row in value["records"]:
            result.setdefault((row["case_id"], "behavior", ""), []).append(row["behavior_pass"])
            for stage, graded in row["stages"].items():
                result.setdefault((row["case_id"], stage, "<stage>"), []).append(graded["passed"])
                for field in graded["fields"]:
                    result.setdefault((row["case_id"], stage, field["path"]), []).append(field["status"] == "correct")
        return result
    before, after = outcomes(baseline), outcomes(report)
    regressions, improvements = [], []
    for key in sorted(before.keys() | after.keys()):
        # An unexpected field absent in the other run is a correct omission.
        old, new = all(before.get(key, [True])), all(after.get(key, [True]))
        entry = {"case_id": key[0], "stage": key[1], "field": key[2]}
        if old and not new:
            regressions.append(entry)
        elif not old and new:
            improvements.append(entry)
    return {"regressions": regressions, "improvements": improvements, "passed": not regressions}


def _report(dataset: Dataset, cases: tuple[Case, ...], records: list[dict], mode: str, label: str, metadata: dict) -> dict:
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "mode": mode, "label": label,
            "dataset": {"name": dataset.name, "version": dataset.version, "fingerprint": dataset.fingerprint,
                        "case_identity": [c.identity for c in cases]},
            "selected_cases": [c.id for c in cases], "service": metadata,
            "passed": all(r["passed"] for r in records), "summary": _summarize(records),
            "by_trade_type": {tt: _summarize([r for r in records if r["trade_type"] == tt]) for tt in sorted({c.trade_type for c in cases})},
            "records": records}


def _csv_value(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def write_report(output: Path, report: dict) -> None:
    _write_json(output / "report.json", report)
    with (output / "fields.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "attempt", "stage", "path", "status", "expected", "actual", "critical"])
        for row in report["records"]:
            for stage, result in row["stages"].items():
                for f in result["fields"]:
                    writer.writerow([_csv_value(v) for v in (row["case_id"], row["attempt"], stage, f["path"], f["status"], f["expected"], f["actual"], f["critical"])])
    esc = lambda x: html.escape(str(x))
    summary = report["summary"]
    blocks = []
    for row in report["records"]:
        fields = []
        errors = []
        for stage, result in row["stages"].items():
            if result.get("error"):
                errors.append(f"<p>{esc(stage)}: {esc(result['error'])}</p>")
            for f in result["fields"]:
                if f["status"] != "correct":
                    fields.append("<tr>" + "".join(f"<td>{esc(v if v is not None else '—')}</td>" for v in
                                  (stage, f["path"], f["status"], f["expected"], f["actual"], "yes" if f["critical"] else "")) + "</tr>")
        status = "PASS" if row["passed"] else "FAIL"
        reason = "" if row["behavior_pass"] else f"<p>Unexpected API outcome: HTTP {esc(row['status_code'])}; {esc(row.get('capture_error') or 'business result mismatch')}</p>"
        blocks.append(f"<details {'open' if not row['passed'] else ''}><summary>{status} · {esc(row['case_id'])} · run {row['attempt']}</summary>{reason}" + "".join(errors) +
                      "<table><thead><tr><th>Stage</th><th>Field</th><th>Result</th><th>Expected</th><th>Actual</th><th>Critical</th></tr></thead><tbody>"
                      + "".join(fields) + "</tbody></table></details>")
    metrics = "".join(f"<tr><td>{esc(stage)}</td><td>{bucket['passed']}/{bucket['attempts']}</td>"
                      f"<td>{esc(bucket['precision'])}</td><td>{esc(bucket['recall'])}</td><td>{bucket['critical_failures']}</td></tr>"
                      for stage, bucket in summary["stages"].items())
    comparison = ""
    if "baseline" in report:
        comparison = (f"<p>Baseline error: {esc(report['baseline']['error'])}</p>" if report["baseline"].get("error") else
                      f"<p>Baseline: {len(report['baseline']['regressions'])} regressions, {len(report['baseline']['improvements'])} improvements.</p>")
    document = ("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Capture evaluation</title>"
                "<style>body{font:16px system-ui;margin:40px auto;max-width:1200px;padding:0 24px;color:#17283c}h1{margin-bottom:8px}"
                "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{text-align:left;border-bottom:1px solid #d9e0e8;padding:10px;overflow-wrap:anywhere}"
                "th{background:#eef3f8}details{border:1px solid #d9e0e8;border-radius:6px;margin:14px 0;padding:14px}summary{cursor:pointer;font-weight:600}"
                "small{color:#52647b}code{overflow-wrap:anywhere}</style>"
                f"<h1>{'PASS' if report['passed'] else 'FAIL'} · {esc(report['dataset']['name'])}</h1>"
                f"<p>{esc(report['label'])} · {summary['passed_attempts']}/{summary['attempts']} attempts pass; "
                f"{summary['consistently_passing_cases']}/{summary['cases']} documents pass every run.</p>"
                f"<p>{summary['unverified_input_attempts']} imported responses without verified PDF/type metadata.</p>"
                "<p>Scores cover the fields selected by the dataset rules. Unlabelled or excluded fields are not certified.</p>"
                f"<small>Dataset {esc(report['dataset']['version'])} · {esc(report['created_at'])}</small>{comparison}"
                "<table><thead><tr><th>Stage</th><th>Pass</th><th>Precision</th><th>Recall</th><th>Critical failures</th></tr></thead><tbody>"
                + metrics + "</tbody></table>" + "".join(blocks) + "</html>")
    (output / "report.html").write_text(document, encoding="utf-8")


def _prepare(output: Path, dataset: Dataset) -> None:
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "dataset.json", dataset.manifest)


def _finish(output: Path, report: dict, baseline: Path | None) -> dict:
    if baseline:
        try:
            previous = json.loads(baseline.read_text(encoding="utf-8"))
            report["baseline"] = compare_baseline(report, previous)
            report["passed"] = report["passed"] and report["baseline"]["passed"]
        except (OSError, ValueError, KeyError, TypeError):
            # Always preserve the new measurements, even if the baseline is unusable.
            report["passed"] = False
            report["baseline"] = {"error": "Incompatible or unreadable baseline", "regressions": [], "improvements": [], "passed": False}
    write_report(output, report)
    return report


def run_dataset(dataset: Dataset, output: Path, client: Any, *, repeat: int = 1, split: str | None = None,
                tags: list[str] | None = None, label: str = "", baseline: Path | None = None,
                progress: Callable[[str], None] | None = None) -> dict:
    if type(repeat) is not int or repeat < 1:
        raise ValueError("repeat must be a positive integer")
    cases = select_cases(dataset, split=split, tags=tags)
    _prepare(output, dataset)
    metadata = client.metadata()
    records = []
    for case in cases:
        for attempt in range(1, repeat + 1):
            if progress:
                progress(f"Capture {len(records) + 1}/{len(cases) * repeat}: {case.id}, attempt {attempt}")
            directory = output / "cases" / case.id / f"run-{attempt:03d}"
            capture = client.capture(case.pdf, case.trade_type, directory)
            records.append(grade_case(case, capture, attempt=attempt, artifacts=str(directory.relative_to(output))))
            # Incremental report keeps completed measurements if a user interrupts a later request.
            partial = _report(dataset, cases, records, "live", label, metadata)
            partial["complete"] = False
            partial["passed"] = False
            _write_json(output / "report.json", partial)
    report = _report(dataset, cases, records, "live", label, metadata)
    report["complete"] = True
    return _finish(output, report, baseline)


def _saved_capture(directory: Path, case: Case) -> dict:
    result: dict = {}
    metadata_file = directory / "run.json"
    try:
        if metadata_file.exists():
            result = json.loads(metadata_file.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError()
            if result.get("pdf_sha256") != case.identity["pdf_sha256"] or result.get("trade_type") != case.trade_type:
                return {"response": None, "status_code": None, "success": False, "artifact_error": True,
                        "error_category": "input_identity_mismatch"}
        json_file = directory / "response.json"
        raw = (json_file if json_file.exists() else directory / "response.body").read_bytes()
        if result.get("response_sha256") and result["response_sha256"] != sha256(raw):
            return {**result, "response": None, "success": False, "artifact_error": True,
                    "error_category": "response_hash_mismatch"}
        decoded = json.loads(raw) if json_file.exists() else None
        body = decoded if isinstance(decoded, dict) else None
        return {**result, "response": body, "status_code": result.get("status_code", 200),
                "success": result.get("success", isinstance(body, dict) and body.get("success") is True)}
    except (OSError, ValueError, UnicodeDecodeError):
        return {**result, "response": None, "success": False, "artifact_error": True,
                "error_category": "missing_or_invalid_saved_response"}


def score_saved(dataset: Dataset, responses: Path, output: Path, *, split: str | None = None,
                tags: list[str] | None = None, label: str = "", baseline: Path | None = None) -> dict:
    cases = select_cases(dataset, split=split, tags=tags)
    if not responses.is_dir():
        raise ValueError("Saved response directory does not exist")
    source = responses / "cases" if (responses / "cases").is_dir() else responses
    _prepare(output, dataset)
    records = []
    for case in cases:
        case_dir = source / case.id
        attempts = sorted(p for p in case_dir.glob("run-*") if p.is_dir()) if case_dir.is_dir() else []
        if not attempts:
            attempts = [case_dir]
        for attempt, directory in enumerate(attempts, 1):
            capture = _saved_capture(directory, case)
            records.append(grade_case(case, capture, attempt=attempt, artifacts=str(directory.resolve())))
    report = _report(dataset, cases, records, "offline", label, {})
    report["complete"] = True
    return _finish(output, report, baseline)
