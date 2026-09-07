"""Opt-in deployed-model evaluation; outputs rubric results, never answer/credential text.

Unlike the offline graph suite this makes real model/tool calls and creates session receipts.
Use only an approved dev tenant with read-only tools and an approved dataset/budget.
"""

import argparse
import json
import time
from pathlib import Path

import httpx
from smoke import check, headers, settings


def grade(case: dict, answer: dict) -> dict:
    text = answer.get("answer_markdown", "").casefold()
    tools = {entry["name"] for entry in answer.get("tool_trace", [])}
    checks = {
        "completed": answer.get("status") == case.get("expected_status", "completed"),
        "persisted": answer.get("persisted") is True,
        "required_text": all(value.casefold() in text for value in case.get("must_contain", [])),
        "forbidden_text": all(
            value.casefold() not in text for value in case.get("must_not_contain", [])
        ),
        "required_tools": set(case.get("required_tools", [])).issubset(tools),
        "forbidden_tools": not set(case.get("forbidden_tools", [])).intersection(tools),
        "no_synthetic_chart": answer.get("chart_spec") is None,
    }
    return {
        "id": case["id"],
        "passed": all(checks.values()),
        "checks": checks,
        "usage": answer.get("usage", {}),
        "human_review": "required",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--confirm-live-readonly-dev", action="store_true")
    parser.add_argument("--max-cases", type=int, default=10)
    args = parser.parse_args()
    if not args.confirm_live_readonly_dev:
        parser.error(
            "Explicit --confirm-live-readonly-dev is required; this uses a real model/tools."
        )
    dataset = json.loads(args.cases.read_text(encoding="utf-8"))
    if not dataset.get("approved_by") or not dataset.get("budget_reference"):
        parser.error("Dataset requires approved_by and budget_reference before live execution.")
    cases = dataset["cases"]
    if not 1 <= len(cases) <= args.max_cases <= 100:
        parser.error("Dataset exceeds the explicit case limit (maximum 100).")
    cfg = settings()
    base = cfg["agent_url"].rstrip("/")
    results = []
    with httpx.Client(timeout=230, follow_redirects=False) as client:
        auth = headers(cfg, client)
        for case in cases:
            sid = check(client.post(base + "/api/sessions", headers=auth))["session_id"]
            try:
                started = time.monotonic()
                answer = check(
                    client.post(
                        base + "/api/chat",
                        headers=auth
                        | {
                            "X-Diapason-Locale": case.get("locale", "en_us"),
                        },
                        json={"session_id": sid, "message": case["message"]},
                    )
                )
                result = grade(case, answer)
                result["duration_ms"] = int((time.monotonic() - started) * 1000)
                results.append(result)
            finally:
                # Soft-delete only this invocation's own session, preserving legacy retention.
                check(client.delete(base + "/api/sessions/" + sid, headers=auth))
    print(json.dumps({"dataset": dataset["name"], "results": results}, indent=2))
    if not all(result["passed"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(
            f"Evaluation failed ({type(exc).__name__}); no answer payload printed."
        ) from None
