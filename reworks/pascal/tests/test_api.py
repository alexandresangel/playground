import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock

from cryptography.fernet import Fernet

from pascal.agent import discovery, mcp
import prompt_loader


def prepare(service, monkeypatch, *, streaming=False):
    monkeypatch.setattr(prompt_loader, "_prompt", "original system prompt")
    calls = []
    def create(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        usage = NS(prompt_tokens=9, completion_tokens=3, total_tokens=12)
        if streaming:
            class Stream:
                def __iter__(self):
                    yield NS(choices=[NS(delta=NS(content="Bonjour", tool_calls=[]))], usage=None)
                    yield NS(choices=[], usage=usage)
                def close(self): pass
            return Stream()
        return NS(choices=[NS(message=NS(content="Bonjour", tool_calls=[]))], usage=usage)
    client = NS(chat=NS(completions=NS(create=create)), close=Mock())
    monkeypatch.setattr(service.runtime, "azure_client", lambda: {"client": client, "deployment": "same-model"})
    def rpc(server, method, params, **kwargs):
        assert method == "tools/list" and params == {}
        return {"tools": [{"name": "balance", "description": "Balance", "inputSchema": {"type": "object"}}]}
    monkeypatch.setattr(discovery, "_mcp_request", rpc)
    monkeypatch.setattr(mcp, "_mcp_request", rpc)
    return client, calls


def test_json_chat_reuses_session_history_model_and_usage(service, monkeypatch):
    client, calls = prepare(service, monkeypatch)
    created = service.client.post("/api/sessions", headers=service.headers).json()
    sid = created["session_id"]
    service.runtime.sessions.append_turn(sid, service.scope, "previous question", "previous answer")
    response = service.client.post("/api/chat", headers=service.headers, json={"message": "Bonjour", "session_id": sid, "client_timezone": "Europe/Paris"})
    assert response.status_code == 200
    assert response.json()["answer_markdown"] == "Bonjour" and response.json()["session_id"] == sid
    messages = calls[0]["messages"]
    assert messages[0]["content"].startswith("original system prompt")
    assert "Europe/Paris" in messages[0]["content"] and "fr_fr" in messages[0]["content"]
    assert [m["content"] for m in messages[1:]] == ["previous question", "previous answer", "Bonjour"]
    record = service.runtime.sessions.get_session(sid, service.scope)
    assert record["turns"][-1]["usage"] == {"input": 9, "output": 3, "total": 12, "cost_usd": 0.0}
    client.close.assert_called_once()


def test_sse_events_session_header_and_single_persistence(service, monkeypatch):
    client, calls = prepare(service, monkeypatch, streaming=True)
    response = service.client.post("/api/chat/stream", headers=service.headers, json={"message": "Bonjour"})
    assert response.status_code == 200
    lines = [line.removeprefix("data: ") for line in response.text.splitlines() if line.startswith("data: ")]
    assert lines[-1] == "[DONE]"
    events = [json.loads(line) for line in lines[:-1]]
    assert [e["type"] for e in events] == ["delta", "done"]
    assert events[0]["content"] == "Bonjour"
    assert events[-1]["session_id"] == response.headers["X-Diapason-Chat-Session"]
    assert len(service.runtime.sessions.writes) == 1
    assert service.runtime.sessions.writes[0][2]["usage"]["total"] == 12
    client.close.assert_called_once()


def test_dynamic_tools_remain_caller_scoped(service, monkeypatch):
    seen = []
    key = service.runtime.config["mcp"]["default"]["config_key"]
    def rpc(server, method, params, **kwargs):
        assert method == "tools/list"
        payload = json.loads(Fernet(key).decrypt(server.request_headers["Authorization"].split()[1].encode()))
        seen.append(payload)
        return {"tools": [{"name": f"scope{payload['scope']}", "inputSchema": {}}]}
    monkeypatch.setattr(discovery, "_mcp_request", rpc)
    first = service.client.get("/api/mcp/tools", headers=service.headers)
    second = service.client.get("/api/mcp/tools", headers={**service.headers, "X-Diapason-Mcp-Scope": "8", "X-Diapason-Mcp-Token": "second-token"})
    assert first.json()["tools"][0]["name"] == "scope3"
    assert second.json()["tools"][0]["name"] == "scope8"
    assert [p["api_token"] for p in seen] == ["private-api-token", "second-token"]


def test_other_user_cannot_read_or_delete_session(service):
    sid = service.runtime.sessions.create_session(service.scope)["session_id"]
    other = {**service.headers, "X-Diapason-User-Id": "99"}
    assert service.client.get(f"/api/sessions/{sid}", headers=other).status_code == 404
    assert service.client.delete(f"/api/sessions/{sid}", headers=other).status_code == 404
    assert service.client.get(f"/api/sessions/{sid}", headers=service.headers).status_code == 200


def test_original_frontend_is_served(service):
    assert service.client.get("/").status_code == 200
    assert service.client.get("/static/agent/agent-widget.js").status_code == 200
    assert service.client.get("/api/i18n?locale=fr_FR").json()["locale"] == "fr_fr"
