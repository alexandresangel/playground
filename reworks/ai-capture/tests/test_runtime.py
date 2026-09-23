from unittest.mock import Mock
import json
import httpx
import pytest
from fastapi.testclient import TestClient

import settings
from capture.application import create_app
from capture import runtime
from capture.workflow import prompts


def test_capture_startup_loads_only_its_catalog_from_service_root(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text('{"registry_url": "https://registry.example/services.json", "capture": {"enabled": true}}')
    monkeypatch.delenv("CHAT_CONFIG", raising=False)
    monkeypatch.setattr(settings, "_config", None)
    monkeypatch.setattr(runtime, "configure_auth", lambda *args: (Mock(), None, None, None))
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


def test_startup_discovers_registry_and_validates_m2m_without_keystore(tmp_path, monkeypatch, m2m_keys, mint_token):
    config = {"registry_url": "https://registry.example/services.json", "capture": {"enabled": True}}
    (tmp_path / "config.local.json").write_text(json.dumps(config))
    (tmp_path / "config").mkdir()
    (tmp_path / "config/catalog.json").write_text('{"version":"startup","prompts":{"loan.txt":["iamLoan"]}}')
    monkeypatch.setattr(settings, "_config", None)
    monkeypatch.delenv("CHAT_CONFIG", raising=False)
    monkeypatch.setattr(runtime.telemetry, "init_otel", lambda **kwargs: None)
    for name in ("_config_dir", "_catalog", "_catalog_version", "_catalog_source", "_prompt_cache"):
        monkeypatch.setattr(prompts, name, getattr(prompts, name))
    requests = []
    def handler(request):
        requests.append(str(request.url))
        if request.url.host == "registry.example":
            return httpx.Response(200, json={"services": {"m2m": {"url": "https://m2m.example/token"}}})
        return httpx.Response(200, json={"keys": [m2m_keys[1]]})
    original_client = httpx.Client
    # Preserve the real HTTP client and registry parser; replace only transport.
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    app = create_app(tmp_path)
    owned_http = app.state.runtime.auth._client
    with TestClient(app) as client:
        response = client.get("/api/capture", headers={"Authorization": "Bearer " + mint_token()})
        assert response.status_code == 200
        assert response.json()["prompt_version"] == "startup"
    assert owned_http.is_closed
    assert requests == [config["registry_url"], "https://m2m.example/.well-known/jwks.json"]
    assert not list(tmp_path.rglob("*.p12"))
    assert not (tmp_path / "data").exists()


def test_catalog_startup_failure_closes_auth(tmp_path, monkeypatch):
    auth = Mock()
    monkeypatch.setattr(runtime, "load_config", lambda base: {"capture": {"enabled": True}})
    monkeypatch.setattr(runtime, "configure_auth", lambda *args: (auth, None, None, None))
    monkeypatch.setattr(runtime.telemetry, "init_otel", lambda **kwargs: None)
    with pytest.raises(RuntimeError, match="Cannot read Capture config"):
        runtime.create_runtime(tmp_path)
    auth.close.assert_called_once()