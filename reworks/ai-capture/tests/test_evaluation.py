"""Offline behavioral tests for dataset validation, batch grading and reports."""

import json
from pathlib import Path

import pytest

from evals.cli import main
from evals.dataset import load_dataset
from evals.runner import compare_baseline, run_dataset, score_saved


GOLD = '<tradeMoneyMarket gracePeriod="2"><amount1>1000000</amount1><currency1 shortname="EUR"/><isFixed>false</isFixed></tradeMoneyMarket>'


def dataset_file(tmp_path, *, cases=None, **extra):
    (tmp_path / "contract.pdf").write_bytes(b"%PDF-1.7\nmock PDF for offline runner tests")
    (tmp_path / "gold.xml").write_text(GOLD, encoding="utf-8")
    content = {"schema_version": 1, "name": "test", "version": "1",
               "cases": cases or [{"id": "loan-1", "pdf": "contract.pdf", "trade_type": "iamLoan",
                                    "expected_xml": "gold.xml", "rules": {"critical_fields": ["amount1", "currency1"]}}], **extra}
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def saved_response(directory, body, **metadata):
    directory.mkdir(parents=True)
    (directory / "response.json").write_text(json.dumps(body), encoding="utf-8")
    if metadata:
        (directory / "run.json").write_text(json.dumps(metadata), encoding="utf-8")


class FakeCapture:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def metadata(self):
        return {"health": {"revision": "offline-test"}}

    def capture(self, pdf, trade_type, output):
        from evals.dataset import sha256
        body, status = next(self.responses)
        self.calls.append((pdf, trade_type))
        metadata = {"success": body.get("success") is True and status == 200, "status_code": status,
                    "pdf_sha256": sha256(pdf.read_bytes()), "trade_type": trade_type, "duration_seconds": 1}
        saved_response(output, body, **metadata)
        return {**metadata, "response": body}


def test_repeated_live_and_offline_regrade_have_same_scores_and_detect_instability(tmp_path):
    dataset = load_dataset(dataset_file(tmp_path))
    wrong = GOLD.replace("1000000", "100000")
    client = FakeCapture([({"success": True, "trade_xml": xml}, 200) for xml in (GOLD, wrong, GOLD)])
    live = run_dataset(dataset, tmp_path / "live", client, repeat=3)
    assert len(client.calls) == 3
    assert live["summary"]["attempts"] == 3
    assert live["summary"]["passed_attempts"] == 2
    assert live["summary"]["unstable_cases"] == ["loan-1"]
    assert live["summary"]["stages"]["resolved"]["critical_failures"] == 1
    offline = score_saved(dataset, tmp_path / "live", tmp_path / "offline")
    assert offline["summary"] == live["summary"]
    assert not offline["passed"]
    for filename in ("report.json", "report.html", "fields.csv", "dataset.json"):
        assert (tmp_path / "offline" / filename).is_file()


def test_failures_stay_in_denominators_and_other_cases_continue(tmp_path):
    cases = [{"id": f"loan-{i}", "pdf": "contract.pdf", "trade_type": "iamLoan", "expected_xml": "gold.xml"} for i in (1, 2)]
    dataset = load_dataset(dataset_file(tmp_path, cases=cases))
    client = FakeCapture([({"detail": "unavailable"}, 502), ({"success": True, "trade_xml": GOLD}, 200)])
    report = run_dataset(dataset, tmp_path / "run", client)
    counts = report["summary"]["stages"]["resolved"]["counts"]
    assert len(client.calls) == 2 and counts["expected"] == 8
    assert counts["correct"] == counts["missing"] == 4
    assert report["summary"]["stages"]["resolved"]["recall"] == 0.5
    assert report["summary"]["behavior_failures"] == 1


def test_distinct_extracted_and_resolved_labels(tmp_path):
    raw = '<tradeMoneyMarket><cpty name="Bank Example"/></tradeMoneyMarket>'
    resolved = '<tradeMoneyMarket><cpty shortname="BANK-EX"/></tradeMoneyMarket>'
    path = dataset_file(tmp_path, cases=[{"id": "loan-1", "pdf": "contract.pdf", "trade_type": "iamLoan",
                                         "expected_xml": "gold.xml", "expected_extracted_xml": "raw.xml"}])
    (tmp_path / "gold.xml").write_text(resolved)
    (tmp_path / "raw.xml").write_text(raw)
    dataset = load_dataset(path)
    client = FakeCapture([({"success": True, "trade_xml": resolved, "debug": {"extract": {"trade_xml": raw}}}, 200)])
    report = run_dataset(dataset, tmp_path / "run", client)
    assert report["passed"] and set(report["summary"]["stages"]) == {"resolved", "extracted"}


@pytest.mark.parametrize("xml", ["<broken", "<wrong><amount1>1000000</amount1></wrong>", ""])
def test_invalid_or_missing_actual_xml_fails_with_expected_fields_counted(tmp_path, xml):
    dataset = load_dataset(dataset_file(tmp_path))
    saved_response(tmp_path / "responses" / "loan-1", {"success": True, "trade_xml": xml})
    report = score_saved(dataset, tmp_path / "responses", tmp_path / "run")
    assert not report["passed"]
    assert report["summary"]["stages"]["resolved"]["counts"]["missing"] == 4


def test_offline_cli_does_not_create_http_client_or_load_api_secrets(tmp_path, monkeypatch):
    import httpx
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline evaluation attempted HTTP")
    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setenv("INTEG_PLATFORM_CONFIG", "invalid secret config must not be read")
    path = dataset_file(tmp_path)
    saved_response(tmp_path / "responses" / "loan-1", {"success": True, "trade_xml": GOLD})
    assert main(["validate", str(path)]) == 0
    assert main(["score", str(path), "--responses", str(tmp_path / "responses"), "--output", str(tmp_path / "run")]) == 0


def test_missing_case_response_is_a_failure_not_a_skip(tmp_path):
    dataset = load_dataset(dataset_file(tmp_path))
    (tmp_path / "responses").mkdir()
    report = score_saved(dataset, tmp_path / "responses", tmp_path / "run")
    assert not report["passed"] and report["summary"]["attempts"] == 1
    assert report["summary"]["stages"]["resolved"]["recall"] == 0


def test_ground_truth_changes_invalidate_baseline_and_saved_pdf_mismatch_fails(tmp_path):
    path = dataset_file(tmp_path)
    dataset = load_dataset(path)
    saved_response(tmp_path / "responses" / "loan-1", {"success": True, "trade_xml": GOLD})
    baseline = score_saved(dataset, tmp_path / "responses", tmp_path / "baseline")
    (tmp_path / "gold.xml").write_text(GOLD.replace("1000000", "1000001"))
    changed = load_dataset(path)
    assert changed.fingerprint != dataset.fingerprint
    candidate = score_saved(changed, tmp_path / "responses", tmp_path / "candidate", baseline=tmp_path / "baseline/report.json")
    assert candidate["baseline"]["error"] and not candidate["passed"]
    with pytest.raises(ValueError, match="different dataset"):
        compare_baseline(candidate, baseline)
    (tmp_path / "responses/loan-1/run.json").write_text(json.dumps({"pdf_sha256": "wrong", "trade_type": "iamLoan", "status_code": 200}))
    report = score_saved(dataset, tmp_path / "responses", tmp_path / "mismatched")
    assert not report["passed"] and report["records"][0]["capture_error"] == "input_identity_mismatch"


def test_baseline_reports_field_regression_even_if_another_field_improves(tmp_path):
    dataset = load_dataset(dataset_file(tmp_path))
    saved_response(tmp_path / "before/loan-1", {"success": True, "trade_xml": GOLD.replace("1000000", "2")})
    saved_response(tmp_path / "after/loan-1", {"success": True, "trade_xml": GOLD.replace("EUR", "USD")})
    baseline = score_saved(dataset, tmp_path / "before", tmp_path / "baseline")
    candidate = score_saved(dataset, tmp_path / "after", tmp_path / "candidate")
    diff = compare_baseline(candidate, baseline)
    assert {r["field"] for r in diff["regressions"]} == {"currency1/@shortname"}
    assert {r["field"] for r in diff["improvements"]} == {"amount1"}


def test_negative_cases_require_expected_http_outcome_not_transport_failure(tmp_path):
    cases = [{"id": "unreadable", "pdf": "contract.pdf", "trade_type": "iamLoan", "expected_success": False, "expected_status": 400}]
    dataset = load_dataset(dataset_file(tmp_path, cases=cases))
    good = run_dataset(dataset, tmp_path / "good", FakeCapture([({"detail": "bad PDF"}, 400)]))
    bad = run_dataset(dataset, tmp_path / "bad", FakeCapture([({}, None)]))
    assert good["passed"] and not bad["passed"]
    assert good["summary"]["stages"] == {}


def test_missing_negative_response_cannot_pass_using_only_saved_status(tmp_path):
    cases = [{"id": "unreadable", "pdf": "contract.pdf", "trade_type": "iamLoan", "expected_success": False, "expected_status": 400}]
    dataset = load_dataset(dataset_file(tmp_path, cases=cases))
    case = dataset.cases[0]
    directory = tmp_path / "responses/unreadable"
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps({"pdf_sha256": case.identity["pdf_sha256"], "trade_type": "iamLoan", "status_code": 400}))
    report = score_saved(dataset, tmp_path / "responses", tmp_path / "report")
    assert not report["passed"]
    assert report["records"][0]["capture_error"] == "missing_or_invalid_saved_response"
    # A preserved non-JSON HTTP rejection is a valid observed outcome.
    (directory / "response.body").write_text("Bad request")
    assert score_saved(dataset, tmp_path / "responses", tmp_path / "report-body")["passed"]


def test_partial_baseline_rejected_and_changed_response_hash_is_not_trusted(tmp_path):
    from copy import deepcopy
    from evals.dataset import sha256
    dataset = load_dataset(dataset_file(tmp_path))
    saved_response(tmp_path / "responses/loan-1", {"success": True, "trade_xml": GOLD})
    report = score_saved(dataset, tmp_path / "responses", tmp_path / "report")
    partial = deepcopy(report)
    partial["complete"] = False
    with pytest.raises(ValueError, match="complete"):
        compare_baseline(report, partial)
    partial["complete"] = True
    partial["records"] = []
    with pytest.raises(ValueError, match="nonempty"):
        compare_baseline(report, partial)
    directory = tmp_path / "responses/loan-1"
    (directory / "run.json").write_text(json.dumps({"pdf_sha256": dataset.cases[0].identity["pdf_sha256"],
        "trade_type": "iamLoan", "response_sha256": sha256(b"different response"), "status_code": 200}))
    mismatch = score_saved(dataset, tmp_path / "responses", tmp_path / "mismatch")
    assert not mismatch["passed"] and mismatch["records"][0]["capture_error"] == "response_hash_mismatch"


@pytest.mark.parametrize("mutation", ["duplicate", "unknown_key", "empty_gold", "bad_rules", "missing_gold", "unsafe_id", "no_cases"])
def test_dataset_validation_catches_bad_labels_before_live_calls(tmp_path, mutation):
    path = dataset_file(tmp_path)
    data = json.loads(path.read_text())
    if mutation == "duplicate":
        data["cases"].append({**data["cases"][0], "id": "LOAN-1"})
    elif mutation == "unknown_key":
        data["cases"][0]["expected_xlm"] = "gold.xml"
    elif mutation == "empty_gold":
        (tmp_path / "gold.xml").write_text("<tradeMoneyMarket/>")
    elif mutation == "bad_rules":
        data["cases"][0]["rules"] = {"include_fields": ["nonexistent"]}
    elif mutation == "missing_gold":
        del data["cases"][0]["expected_xml"]
    elif mutation == "unsafe_id":
        data["cases"][0]["id"] = "../elsewhere"
    else:
        data["cases"] = []
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_dataset(path)


def test_existing_output_and_empty_selection_do_not_call_api(tmp_path):
    dataset = load_dataset(dataset_file(tmp_path))
    client = FakeCapture([])
    (tmp_path / "run").mkdir()
    with pytest.raises(FileExistsError):
        run_dataset(dataset, tmp_path / "run", client)
    with pytest.raises(ValueError, match="No dataset cases"):
        run_dataset(dataset, tmp_path / "new", client, split="holdout")
    assert client.calls == [] and not (tmp_path / "new").exists()


def test_html_escapes_document_values(tmp_path):
    path = dataset_file(tmp_path)
    dataset = load_dataset(path)
    evil = GOLD.replace("EUR", "&lt;script&gt;alert(1)&lt;/script&gt;")
    saved_response(tmp_path / "responses/loan-1", {"success": True, "trade_xml": evil})
    score_saved(dataset, tmp_path / "responses", tmp_path / "report", label="<script>bad</script>")
    rendered = (tmp_path / "report/report.html").read_text(encoding="utf-8")
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
