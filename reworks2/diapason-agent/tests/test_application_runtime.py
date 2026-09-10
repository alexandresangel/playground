"""Relocation keeps company configuration rooted in the service directory."""

import json
from unittest.mock import MagicMock

from pascal import runtime
import prompt_loader
import settings


def test_startup_retains_root_config_and_both_prompt_loaders(tmp_path, monkeypatch):
    config = {"intelligence_contract": {"enabled": True}, "azure_openai": {}}
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.delenv("CHAT_CONFIG", raising=False)
    monkeypatch.setattr(settings, "_config", None)
    auth = MagicMock(return_value=(object(), *[lambda: None for _ in range(4)]))
    sessions = object()
    prompts = MagicMock()
    system_prompt = MagicMock()
    monkeypatch.setattr(prompt_loader, "init_system_prompt", system_prompt)
    monkeypatch.setattr(runtime, "configure_auth", auth)
    monkeypatch.setattr(runtime, "create_session_store", lambda cfg: sessions)
    monkeypatch.setattr(runtime, "init_capture_prompts", prompts)
    monkeypatch.setattr(runtime.telemetry, "init_otel", lambda **kwargs: None)
    monkeypatch.setattr(runtime.logging, "basicConfig", lambda **kwargs: None)
    monkeypatch.setattr(runtime.build_info, "_VERSION_FILE", tmp_path / "VERSION")
    services = runtime.create_runtime(tmp_path)
    assert services.config == config and services.sessions is sessions
    auth.assert_called_once_with(tmp_path, config)
    prompts.assert_called_once_with(config)
    assert services.azure_client() is None
    system_prompt.assert_called_once_with(config, tmp_path)
