from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import settings
from dia_jwt import JwtAuth
from dia_jwt.fastapi import jwt_deps
from capture.application import create_app
from capture.runtime import Runtime


@pytest.fixture
def service(tmp_path, monkeypatch):
    auth = JwtAuth.create_keystore(tmp_path / "key.p12", "offline-test", revocation_path=tmp_path / "revoked.json")
    config = {
        "intelligence_contract": {"enabled": True},
        "mcp": {"default": {"server_url": "https://mcp.example/mcp", "config_key": Fernet.generate_key().decode()}},
    }
    monkeypatch.setattr(settings, "_config", config)
    deps = jwt_deps(auth)
    runtime = Runtime(Path(__file__).resolve().parents[1], config, auth, **deps)
    app = create_app(runtime.base_dir, runtime=runtime)
    token = auth.mint(sub="instance:demo", roles=["chat"], customer_id=7)
    headers = {
        "Authorization": "Bearer " + token["access_token"],
        "X-Diapason-User-Id": "42", "X-Diapason-Customer-Id": "7",
        "X-Diapason-Mcp-Token": "private-api-token", "X-Diapason-Mcp-Scope": "3",
        "X-Diapason-Mcp-Base-Url": "https://company.example", "X-Diapason-Locale": "fr_FR",
    }
    with TestClient(app) as client:
        yield SimpleNamespace(runtime=runtime, app=app, client=client, headers=headers, token=token, scope="demo/7/42")