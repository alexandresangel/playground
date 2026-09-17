"""Capture configuration takes precedence over its legacy deployment alias."""

import pytest

from capture.workflow.prompts import capture_config, capture_enabled, capture_temperature


@pytest.mark.parametrize("capture", [{"enabled": False, "temperature": 0.2}, {}, None, "invalid"])
def test_capture_block_takes_precedence_over_legacy_settings(capture):
    config = {"capture": capture, "intelligence_contract": {"enabled": True, "temperature": 0.9}}
    assert capture_config(config) == (capture if isinstance(capture, dict) else {})
    assert capture_enabled(config) is False


def test_legacy_settings_remain_supported():
    config = {"intelligence_contract": {"enabled": True, "temperature": 0.9}}
    assert capture_config(config) == config["intelligence_contract"]
    assert capture_enabled(config) is True
    assert capture_temperature(config) == 0.9


@pytest.mark.parametrize(
    "enabled,expected", [(True, True), (False, False), ("true", False), (1, False), (None, False)]
)
def test_enabled_requires_boolean_true(enabled, expected):
    assert capture_enabled({"capture": {"enabled": enabled}}) is expected


@pytest.mark.parametrize(
    "raw,expected", [(0, 0.0), (0.2, 0.2), ("0.7", 0.7), (None, 0.5), ("invalid", 0.5)]
)
def test_temperature_conversion_and_fallback(raw, expected):
    assert capture_temperature({"capture": {"temperature": raw}}) == expected
