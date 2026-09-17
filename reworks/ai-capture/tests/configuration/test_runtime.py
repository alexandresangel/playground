"""Startup config location and Azure client lifecycle configuration."""

from unittest.mock import Mock
import json

import pytest

import settings
from capture import runtime
from capture.workflow import prompts


def test_capture_startup_loads_only_its_catalog_from_service_root(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text('{"capture": {"enabled": true}}')
    monkeypatch.delenv("CHAT_CONFIG", raising=False)
    monkeypatch.setattr(settings, "_config", None)
    monkeypatch.setattr(runtime, "configure_auth", lambda *args: (None, None, None, None, None))
    monkeypatch.setattr(runtime.telemetry, "init_otel", lambda **kwargs: None)
    monkeypatch.setattr(runtime.telemetry, "get_tracer", lambda *args: None)
    monkeypatch.setattr(runtime.logging, "basicConfig", lambda **kwargs: None)
    monkeypatch.setattr(runtime.build_info, "_VERSION_FILE", runtime.build_info._VERSION_FILE)
    for logger in (
        "azure",
        "httpx",
        "httpcore",
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        "opentelemetry.exporter.otlp.proto.http._log_exporter",
    ):
        target = runtime.logging.getLogger(logger)
        monkeypatch.setattr(target, "level", target.level)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "catalog.json").write_text(
        json.dumps({"version": "local-1", "prompts": {"prompt.txt": ["test"]}})
    )
    (config_dir / "prompt.txt").write_text("Local extraction prompt", encoding="utf-8")
    monkeypatch.chdir(tmp_path.parent)
    result = runtime.create_runtime(tmp_path)
    assert "storage" not in result.config
    assert not hasattr(result, "sessions")
    assert prompts.capture_prompt_source() == str(config_dir / "catalog.json")
    assert prompts.capture_prompt_version() == "local-1"
    assert prompts.get_prompt_text(result.config, "prompt.txt") == "Local extraction prompt"
    assert not (tmp_path / "system_prompt.md").exists()


def test_azure_constructor_receives_configured_connection_arguments(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(runtime, "AzureOpenAI", constructor)
    config = {
        "azure_openai": {
            "endpoint": "https://same.openai.azure.com",
            "api_key": "test",
            "deployment": "same-model",
            "api_version": "2024-10-21",
        }
    }
    result = runtime.build_azure_client(config)
    constructor.assert_called_once_with(
        azure_endpoint="https://same.openai.azure.com", api_key="test", api_version="2024-10-21"
    )
    assert result == {"client": constructor.return_value, "deployment": "same-model"}


@pytest.mark.parametrize("missing", ["endpoint", "api_key", "deployment"])
def test_incomplete_azure_config_does_not_construct_client(monkeypatch, missing):
    constructor = Mock()
    monkeypatch.setattr(runtime, "AzureOpenAI", constructor)
    config = {"endpoint": "https://test.openai.azure.com", "api_key": "test", "deployment": "model"}
    config[missing] = " "
    assert runtime.build_azure_client({"azure_openai": config}) is None
    constructor.assert_not_called()


def test_azure_config_is_trimmed_and_default_api_version_is_used(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(runtime, "AzureOpenAI", constructor)
    result = runtime.build_azure_client(
        {
            "azure_openai": {
                "endpoint": " https://test.openai.azure.com ",
                "api_key": " test ",
                "deployment": " model ",
            }
        }
    )
    constructor.assert_called_once_with(
        azure_endpoint="https://test.openai.azure.com", api_key="test", api_version="2024-10-21"
    )
    assert result["deployment"] == "model"
