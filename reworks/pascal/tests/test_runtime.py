import importlib
from pathlib import Path
from unittest.mock import Mock

import prompt_loader
import settings

from pascal import runtime


def test_runtime_uses_service_root_and_never_loads_capture_prompts(tmp_path, monkeypatch):
    config = {"intelligence_contract": {"enabled": True}}
    (tmp_path / "config.json").write_text('{"intelligence_contract": {"enabled": true}}')
    monkeypatch.delenv("CHAT_CONFIG", raising=False)
    monkeypatch.setattr(settings, "_config", None)
    auth = Mock(return_value=(None, None, None, None, None))
    sessions = Mock()
    prompt = Mock()
    monkeypatch.setattr(runtime, "configure_auth", auth)
    monkeypatch.setattr(runtime, "create_session_store", sessions)
    monkeypatch.setattr(prompt_loader, "init_system_prompt", prompt)
    monkeypatch.setattr(runtime.telemetry, "init_otel", lambda **kwargs: None)
    result = runtime.create_runtime(tmp_path)
    assert result.config == config
    auth.assert_called_once_with(tmp_path, config)
    prompt.assert_called_once_with(config, tmp_path)
    assert result.sessions is sessions.return_value


def test_original_azure_constructor_arguments(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(runtime, "AzureOpenAI", constructor)
    config = {"azure_openai": {"endpoint": "https://same.openai.azure.com", "api_key": "test", "deployment": "same-model", "api_version": "2024-10-21"}}
    result = runtime.build_azure_client(config)
    constructor.assert_called_once_with(azure_endpoint="https://same.openai.azure.com", api_key="test", api_version="2024-10-21")
    assert result == {"client": constructor.return_value, "deployment": "same-model"}
    assert runtime.build_azure_client({}) is None
