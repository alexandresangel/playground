"""Offline app bootstrap: real company JWT; only Blob/model/network are substituted."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

PROJECT = Path(__file__).resolve().parents[1]

import auth_setup
import session_store
import settings
from dia_jwt import JwtAuth
from dia_jwt.fastapi import jwt_deps


class MemorySessions:
    """Test double at the unchanged storage interface, not a delivered memory backend."""
    backend = "test"

    def __init__(self):
        self.records = {}
        self.appended = []

    def create_session(self, scope, title=""):
        sid = f"session-{len(self.records) + 1}"
        record = {"session_id": sid, "scope": scope, "created_at": "2026-01-01", "updated_at": "2026-01-01", "turns": []}
        self.records[(scope, sid)] = record
        return record

    def resolve_session_id(self, scope, session_id):
        if session_id:
            if (scope, session_id) not in self.records:
                raise KeyError(session_id)
            return session_id
        return self.create_session(scope)["session_id"]

    def get_session(self, session_id, scope):
        return self.records.get((scope, session_id))

    def get_turns(self, session_id, scope):
        return self.records[(scope, session_id)]["turns"]

    def append_turn(self, session_id, scope, user, assistant, **kwargs):
        self.appended.append((session_id, scope, user, assistant, kwargs))
        self.records[(scope, session_id)]["turns"].extend([
            {"role": "user", "content": user}, {"role": "assistant", "content": assistant},
        ])

    def list_sessions(self, scope):
        return [v for (s, _), v in self.records.items() if s == scope]

    def delete_session(self, session_id, scope):
        return self.records.pop((scope, session_id), None) is not None


def pytest_configure(config):
    # Keep all test keys, caches and temporary files inside this standalone project.
    artifacts = PROJECT / ".pytest-artifacts"
    artifacts.mkdir(exist_ok=True)
    config.option.basetemp = str(artifacts / "tmp")
    key = Fernet.generate_key().decode()
    cfg = {"intelligence_contract": {"enabled": False}, "azure_openai": {},
           "storage": {}, "mcp": {"default": {"server_url": "https://mcp.test/mcp", "config_key": key}},
           "ui": {}, "sessions": {}}
    auth = JwtAuth.create_keystore(artifacts / "test.p12", "test-only", revocation_path=artifacts / "revoked.json")
    if auth._revoked_path.exists():
        auth._revoked_path.unlink()
    deps = jwt_deps(auth)
    configured = (auth, deps["get_identity"], deps["require_admin"], deps["require_refresh"], deps["require_chat"])
    settings._config = cfg
    from capture.runtime import Runtime
    from capture.application import create_app
    services = Runtime(PROJECT, cfg, auth, deps["get_identity"], deps["require_admin"],
                       deps["require_refresh"], deps["require_chat"], MemorySessions())
    app = create_app(PROJECT, runtime=services)
    capture_routes = importlib.import_module("capture.api.extraction")
    config._offline = SimpleNamespace(app=app, runtime=services, auth=auth, cfg=cfg, key=key,
        configured=configured, capture_routes=capture_routes, profile="capture")



@pytest.fixture
def offline(request, monkeypatch):
    runtime = request.config._offline
    sessions = MemorySessions()
    monkeypatch.setattr(runtime.runtime, "sessions", sessions)
    monkeypatch.setitem(runtime.cfg["intelligence_contract"], "enabled", False)
    monkeypatch.setitem(runtime.cfg, "azure_openai", {})
    runtime.sessions = sessions
    return runtime


@pytest.fixture
def headers(offline):
    token = offline.auth.mint(sub="instance:test", roles=["chat"], customer_id=7)["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Diapason-User-Id": "9", "X-Diapason-Customer-Id": "7",
            "X-Diapason-Mcp-Token": "user-specific-api-token", "X-Diapason-Mcp-Scope": "12",
            "X-Diapason-Mcp-Base-Url": "https://company.test/diapason"}
