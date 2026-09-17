"""Normalize only the completion usage consumed by Capture model spans."""

from types import SimpleNamespace

import pytest

from telemetry import usage_from_completion


@pytest.mark.parametrize(
    "response,expected",
    [
        pytest.param(
            SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18)
            ),
            {"input": 11, "output": 7, "total": 18},
            id="sdk-completion",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 11, "completion_tokens": 7}},
            {"input": 11, "output": 7, "total": 18},
            id="dict-computed-total",
        ),
        pytest.param(
            {"usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}},
            {"input": 11, "output": 7, "total": 18},
            id="alternate-token-names",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}},
            {"input": 0, "output": 0, "total": 0},
            id="zero-usage",
        ),
        pytest.param(SimpleNamespace(usage=None), {}, id="no-sdk-usage"),
        pytest.param({}, {}, id="no-dict-usage"),
        pytest.param(
            {"usage": {"prompt_tokens": "bad", "completion_tokens": None}},
            {},
            id="nonnumeric-usage",
        ),
    ],
)
def test_completion_usage_normalization(response, expected):
    assert usage_from_completion(response) == expected
