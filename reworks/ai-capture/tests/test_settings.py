"""Configuration precedence and mandatory registry discovery."""

import json

import pytest

import settings


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    monkeypatch.setattr(settings, "_config", None)
    monkeypatch.delenv("CHAT_CONFIG", raising=False)


def test_env_overrides_local_and_default(tmp_path, monkeypatch):
    (tmp_path / "config.local.json").write_text("invalid")
    (tmp_path / "config.json").write_text("invalid")
    config = {"registry_url": "https://registry.example/services.json"}
    monkeypatch.setenv("CHAT_CONFIG", json.dumps(config))
    assert settings.load_config(tmp_path) == config


def test_local_overrides_default_and_default_remains_supported(tmp_path, monkeypatch):
    for name in ("config.json", "config.local.json"):
        (tmp_path / name).write_text(json.dumps({"registry_url": "https://registry.example/services.json", "source": name}))
    assert settings.load_config(tmp_path)["source"] == "config.local.json"
    (tmp_path / "config.local.json").unlink()
    monkeypatch.setattr(settings, "_config", None)
    assert settings.load_config(tmp_path)["source"] == "config.json"


@pytest.mark.parametrize("body", ["{}", '{"registry_url": "  "}', '{"registry_url": 123}'])
def test_registry_is_required_in_config_not_separate_env(tmp_path, monkeypatch, body):
    monkeypatch.setenv("REGISTRY_URL", "https://registry.example/services.json")
    monkeypatch.setenv("CHAT_CONFIG", body)
    with pytest.raises(RuntimeError, match="registry_url"):
        settings.load_config(tmp_path)


def test_invalid_preferred_config_does_not_fall_back(tmp_path):
    (tmp_path / "config.local.json").write_text("not json")
    (tmp_path / "config.json").write_text('{"registry_url": "https://registry.example/services.json"}')
    with pytest.raises(RuntimeError, match="Invalid JSON"):
        settings.load_config(tmp_path)
