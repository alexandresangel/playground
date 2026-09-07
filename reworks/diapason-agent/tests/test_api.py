import json
from pathlib import Path

import pytest
from conftest import FakeMcp, FakeModel, MemoryStore
from fastapi.testclient import TestClient

from pascal.main import create_app


@pytest.fixture
def client(config, auth):
    app = create_app(
        config=config,
        auth=auth,
        model=FakeModel(),
        transport=FakeMcp(),
        store=MemoryStore(),
        prompt_text="You are Pascal.",
        root=Path.cwd(),
    )
    with TestClient(app) as client:
        yield client


def test_json_chat_and_session_contract(client, headers):
    response = client.post("/api/chat", headers=headers, json={"message": "Hello"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_markdown"] == "Hello"
    assert body["mode"] == "mcp-http+azure-tool-calling"
    assert body["chart_spec"] is None
    sid = body["session_id"]
    assert response.headers["X-Diapason-Chat-Session"] == sid
    detail = client.get(f"/api/sessions/{sid}", headers=headers).json()
    assert [turn["role"] for turn in detail["turns"]] == ["user", "assistant"]
    assert client.get("/api/sessions", headers=headers).json()["sessions"][0]["has_response"]
    assert client.delete(f"/api/sessions/{sid}", headers=headers).json() == {"ok": True}
    assert client.get(f"/api/sessions/{sid}", headers=headers).status_code == 404


def test_sse_wire_contract_done_after_persistence(client, headers):
    response = client.post("/api/chat/stream", headers=headers, json={"message": "Hello"})
    assert response.status_code == 200
    frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    assert frames[-1] == "[DONE]"
    events = [json.loads(frame) for frame in frames[:-1]]
    assert events[0] == {"type": "delta", "content": "Hello"}
    assert events[-1]["type"] == "done"
    assert events[-1]["persisted"] is True
    assert client.app.state.store.writes == 1


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"Authorization": "Bearer invalid"}, 401),
        ({"X-Diapason-Customer-Id": "13"}, 403),
        ({"X-Diapason-User-Id": "x"}, 400),
        ({"X-Diapason-Mcp-Scope": "x"}, 400),
        ({"X-Diapason-Mcp-Token": ""}, 400),
    ],
)
def test_security_rejections(client, headers, change, expected):
    response = client.post("/api/chat", headers=headers | change, json={"message": "Hello"})
    assert response.status_code == expected
    assert not client.app.state.model.requests


def test_tenant_session_isolation(client, headers):
    sid = client.post("/api/sessions", headers=headers).json()["session_id"]
    other = headers | {"X-Diapason-User-Id": "8"}
    assert client.get(f"/api/sessions/{sid}", headers=other).status_code == 404
    assert (
        client.post(
            "/api/chat", headers=other, json={"message": "Hello", "session_id": sid}
        ).status_code
        == 404
    )


def test_health_i18n_and_hidden_tools(client, headers):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    assert client.get("/api/i18n?locale=fr_FR").json()["locale"] == "fr_fr"
    listing = client.get("/api/mcp/tools", headers=headers).json()
    assert listing["tools"][0]["name"] == "balance"
    assert client.get("/api/skills/intelligence-contract", headers=headers).status_code == 404


def test_admin_refresh_roles_not_conflated(client, headers, auth):
    admin = auth.mint(sub="instance:demo", roles=["admin"], customer_id=12)["access_token"]
    admin_headers = headers | {"Authorization": "Bearer " + admin}
    assert client.post("/api/refresh-prompt", headers=admin_headers).status_code == 401
    response = client.post(
        "/api/auth/tokens",
        headers=admin_headers,
        json={"sub": "instance:demo", "roles": ["chat"], "customer_id": 12},
    )
    assert response.status_code == 200
    minted = response.json()
    claims = auth.validate(minted["access_token"])
    assert (
        client.post(
            "/api/auth/revoke", headers=admin_headers, json={"jti": claims["jti"]}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/chat",
            headers=headers | {"Authorization": "Bearer " + minted["access_token"]},
            json={"message": "Hello"},
        ).status_code
        == 401
    )
