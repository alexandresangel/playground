#!/usr/bin/env python3
"""Unit tests for session summary helpers (no live API)."""

from __future__ import annotations

import sys
from pathlib import Path


from session_store import _add_turns, _has_assistant_response, _normalize_tool_trace, _summary, turns_for_client


def test_has_assistant_response() -> None:
    assert not _has_assistant_response([])
    assert not _has_assistant_response([{"role": "user", "content": "hi"}])
    assert _has_assistant_response(
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    )


def test_summary_has_response_flag() -> None:
    s = _summary(
        {
            "session_id": "x",
            "title": "t",
            "created_at": "a",
            "updated_at": "b",
            "turns": [{"role": "assistant", "content": "ok"}],
        }
    )
    assert s["has_response"] is True


def test_normalize_tool_trace() -> None:
    trace = _normalize_tool_trace(
        [{"name": "foo", "arguments": {"a": 1}, "duration_ms": 12}, {"bad": True}]
    )
    assert trace == [{"name": "foo", "tool": "foo", "arguments": {"a": 1}, "duration_ms": 12}]


def test_add_turns_persists_tool_trace() -> None:
    record: dict = {"turns": []}
    _add_turns(
        record,
        "hi",
        "hello",
        30,
        tool_trace=[{"name": "getBalance", "arguments": {"scope": "DEMO"}, "duration_ms": 5}],
    )
    assert len(record["turns"]) == 2
    assistant = record["turns"][1]
    assert assistant["role"] == "assistant"
    assert len(assistant["tool_trace"]) == 1
    assert assistant["tool_trace"][0]["name"] == "getBalance"


def test_add_turns_persists_skill_run() -> None:
    record: dict = {"turns": []}
    _add_turns(
        record,
        "hi",
        "hello",
        30,
        skill_run={
            "skill": "intelligence-contract",
            "trade_type": "mltLoan",
            "artifacts": {"source_trade_xml": "<trade/>"},
        },
    )
    assistant = record["turns"][1]
    assert assistant["skill_run"]["skill"] == "intelligence-contract"
    assert assistant["skill_run"]["artifacts"]["source_trade_xml"] == "<trade/>"
    stripped = turns_for_client(record["turns"])
    assert "skill_run" not in stripped[1]


def test_add_turns_persists_usage() -> None:
    record: dict = {"turns": []}
    _add_turns(
        record,
        "hi",
        "hello",
        30,
        usage={"input": 10, "output": 20, "total": 30, "cost_usd": 0.001},
    )
    assert record["turns"][1]["usage"] == {
        "input": 10,
        "output": 20,
        "total": 30,
        "cost_usd": 0.001,
    }


if __name__ == "__main__":
    test_has_assistant_response()
    test_summary_has_response_flag()
    test_normalize_tool_trace()
    test_add_turns_persists_tool_trace()
    test_add_turns_persists_skill_run()
    test_add_turns_persists_usage()
    print("OK")
