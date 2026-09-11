from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import settings
from dia_jwt import JwtAuth
from dia_jwt.fastapi import jwt_deps
from session_store import _add_turns, turns_for_client
from capture.application import create_app
from capture.runtime import Runtime


class MemorySessions:
    """Test storage using the original record/turn helpers, with strict scope lookup."""
    backend = "test-memory"

    def __init__(self):
        self.records = {}
        self.writes = []

    def create_session(self, scope):
        sid = f"session-{len(self.records) + 1}"
        record = dict(session_id=sid, created_at="now", updated_at="now", turns=[])
        self.records[scope, sid] = record
        return record

    def get_session(self, sid, scope):
        return self.records.get((scope, sid))

    def resolve_session_id(self, scope, sid):
        if sid:
            if (scope, sid) not in self.records:
                raise KeyError(sid)
            return sid
        return self.create_session(scope)["session_id"]

    def append_turn(self, sid, scope, user, assistant, **kwargs):
        record = self.records[scope, sid]
        _add_turns(record, user, assistant, 30, **kwargs)
        self.writes.append((sid, scope, kwargs))

    def get_turns(self, sid, scope):
        return turns_for_client(self.records[scope, sid]["turns"])

    def list_sessions(self, scope):
        return [record for (owner, _), record in self.records.items() if owner == scope]

    def delete_session(self, sid, scope):
        return self.records.pop((scope, sid), None) is not None


@pytest.fixture
def service(tmp_path, monkeypatch):
    auth = JwtAuth.create_keystore(tmp_path / "key.p12", "offline-test", revocation_path=tmp_path / "revoked.json")
    config = {
        "intelligence_contract": {"enabled": True},
        "mcp": {"default": {"server_url": "https://mcp.example/mcp", "config_key": Fernet.generate_key().decode()}},
    }
    monkeypatch.setattr(settings, "_config", config)
    deps = jwt_deps(auth)
    runtime = Runtime(Path(__file__).resolve().parents[1], config, auth, sessions=MemorySessions(), **deps)
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
