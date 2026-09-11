#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


from tool_audience import (
    audience_from_raw,
    is_chat_api_listed,
    is_technical_tool_name,
    is_tool_mentionable,
)


def test_audience_from_meta() -> None:
    assert audience_from_raw({}) == "user"
    assert audience_from_raw({"_meta": {"audience": "technical"}}) == "technical"
    assert is_chat_api_listed("user")
    assert not is_chat_api_listed("technical")


def test_technical_by_name() -> None:
    assert is_technical_tool_name("getMcpServerVersion")
    assert is_technical_tool_name("getDiapasonVersion")
    assert is_technical_tool_name("executePivotModel")
    assert is_technical_tool_name("executePivotModelPage")
    assert not is_technical_tool_name("getValueStatement")
    assert audience_from_raw({"name": "getMcpServerVersion"}) == "technical"
    assert audience_from_raw({"name": "executePivotModelAggregated"}) == "technical"


def test_mentionable_technical() -> None:
    assert not is_tool_mentionable("getMcpServerVersion", "getMcpServerVersion", "technical", [])
    assert is_tool_mentionable("getValueStatement", "getValueStatement", "user", [])
    assert not is_tool_mentionable(
        "getFooPage", "getFooPage", "user", ["*Page"]
    )


if __name__ == "__main__":
    test_audience_from_meta()
    test_technical_by_name()
    test_mentionable_technical()
    print("OK")
