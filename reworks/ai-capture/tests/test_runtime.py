from unittest.mock import Mock
import json

import settings
from capture import runtime
from capture.workflow import prompts


def test_capture_startup_loads_only_its_catalog_from_service_root(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text('{"intelligence_contract": {"enabled": true}}')
    monkeypatch.delenv("CHAT_CONFIG", raising=False)
    monkeypatch.setattr(settings, "_config", None)
    monkeypatch.setattr(runtime, "configure_auth", lambda *args: (None, None, None, None, None))
    monkeypatch.setattr(runtime.telemetry, "init_otel", lambda **kwargs: None)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "catalog.json").write_text(json.dumps({"version": "local-1", "prompts": {"prompt.txt": ["test"]}}))
    (config_dir / "prompt.txt").write_text("Local extraction prompt", encoding="utf-8")
    for name in ("_config_dir", "_catalog", "_catalog_version", "_catalog_source", "_prompt_cache"):
        monkeypatch.setattr(prompts, name, getattr(prompts, name))
    monkeypatch.chdir(tmp_path.parent)
    result = runtime.create_runtime(tmp_path)
    assert "storage" not in result.config
    assert not hasattr(result, "sessions")
    assert prompts.capture_prompt_source() == str(config_dir / "catalog.json")
    assert prompts.capture_prompt_version() == "local-1"
    assert prompts.get_prompt_text(result.config, "prompt.txt") == "Local extraction prompt"
    assert not (tmp_path / "system_prompt.md").exists()


def test_original_azure_constructor_arguments(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(runtime, "AzureOpenAI", constructor)
    config = {"azure_openai": {"endpoint": "https://same.openai.azure.com", "api_key": "test", "deployment": "same-model", "api_version": "2024-10-21"}}
    result = runtime.build_azure_client(config)
    constructor.assert_called_once_with(azure_endpoint="https://same.openai.azure.com", api_key="test", api_version="2024-10-21")
    assert result == {"client": constructor.return_value, "deployment": "same-model"}
