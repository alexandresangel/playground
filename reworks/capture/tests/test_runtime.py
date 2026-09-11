from unittest.mock import Mock

import settings
from capture import runtime


def test_capture_startup_loads_only_its_catalog_from_service_root(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text('{"intelligence_contract": {"enabled": true}}')
    monkeypatch.delenv("CHAT_CONFIG", raising=False)
    monkeypatch.setattr(settings, "_config", None)
    monkeypatch.setattr(runtime, "configure_auth", lambda *args: (None, None, None, None, None))
    monkeypatch.setattr(runtime, "create_session_store", lambda config: None)
    monkeypatch.setattr(runtime.telemetry, "init_otel", lambda **kwargs: None)
    catalog = Mock()
    monkeypatch.setattr(runtime, "init_capture_prompts", catalog)
    result = runtime.create_runtime(tmp_path)
    catalog.assert_called_once_with(result.config)
    assert not (tmp_path / "system_prompt.md").exists()


def test_original_azure_constructor_arguments(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(runtime, "AzureOpenAI", constructor)
    config = {"azure_openai": {"endpoint": "https://same.openai.azure.com", "api_key": "test", "deployment": "same-model", "api_version": "2024-10-21"}}
    result = runtime.build_azure_client(config)
    constructor.assert_called_once_with(azure_endpoint="https://same.openai.azure.com", api_key="test", api_version="2024-10-21")
    assert result == {"client": constructor.return_value, "deployment": "same-model"}
