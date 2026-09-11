#!/usr/bin/env python3
"""Unit tests for chat cost / preview helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


from telemetry import (
    estimate_cost_usd,
    merge_usage,
    query_preview,
    session_blob_url,
    skills_csv,
    tools_csv,
    usage_from_completion,
)


def test_query_preview_truncates() -> None:
    assert query_preview("hello") == "hello"
    long = "x" * 200
    assert len(query_preview(long)) == 120
    assert query_preview(long).endswith("…")


def test_usage_and_cost() -> None:
    u = usage_from_completion(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)))
    assert u == {"input": 1000, "output": 500, "total": 1500}
    merged = merge_usage(u, {"input": 10, "output": 20, "total": 30})
    assert merged == {"input": 1010, "output": 520, "total": 1530}
    cost = estimate_cost_usd(u, {"input_usd_per_1m": 1.0, "output_usd_per_1m": 2.0})
    assert cost == (1000 * 1.0 + 500 * 2.0) / 1_000_000.0


def test_blob_url_and_csv() -> None:
    url = session_blob_url(
        {"storage": {"account_name": "diapasondevstor", "chat_container": "chat-sessions"}},
        "inst/1/2",
        "abc",
    )
    assert url == "https://diapasondevstor.blob.core.windows.net/chat-sessions/inst/1/2/abc.json"
    assert tools_csv([{"name": "Balance"}, {"name": "Balance"}, {"tool": "Movements"}]) == "Balance,Movements"
    assert skills_csv({"skill": "intelligence-contract"}) == "intelligence-contract"


if __name__ == "__main__":
    test_query_preview_truncates()
    test_usage_and_cost()
    test_blob_url_and_csv()
    print("OK")
