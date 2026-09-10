"""Exercise retained HTTP/auth/session contracts without a live environment."""

import json
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

CAPTURE_PATH = "/api/skills/intelligence-contract"


def test_public_health_and_auth_roles(offline, headers):
    client = TestClient(offline.app)
    assert client.get("/health").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/i18n").status_code == 404
    assert client.get("/").status_code == 404
    assert client.post("/api/chat", json={"message": "hello"}).status_code == 404
    assert client.get(CAPTURE_PATH).status_code in (401, 403)
    assert client.get(CAPTURE_PATH, headers=headers).json() == {"detail": "Intelligence contract skill is disabled"}
    assert client.post("/api/auth/tokens", headers=headers, json={"sub": "test", "roles": ["chat"]}).status_code == 401
    assert client.post("/api/refresh-prompt", headers=headers).status_code == 401


def test_identity_customer_user_and_session_binding(offline, headers, monkeypatch):
    client = TestClient(offline.app)
    monkeypatch.setitem(offline.cfg["intelligence_contract"], "enabled", True)
    monkeypatch.setattr(offline.runtime, "azure_client", lambda: {"client": MagicMock(), "deployment": "same"})
    sid = offline.sessions.create_session("test/7/9")["session_id"]
    files = {"pdf": ("bad.pdf", b"not pdf", "application/pdf")}
    data = {"trade_type": "loan", "session_id": sid}
    # The owning user passes the session lookup and reaches PDF validation.
    assert client.post(CAPTURE_PATH, headers=headers, files=files, data=data).json()["detail"] == "File is not a PDF (%PDF- header missing)"
    assert client.post(CAPTURE_PATH, headers={**headers, "X-Diapason-User-Id": "10"}, files=files, data=data).status_code == 404
    assert client.post(CAPTURE_PATH, headers={**headers, "X-Diapason-Customer-Id": "8"}, files=files, data=data).status_code == 403
    assert client.post(CAPTURE_PATH, headers={**headers, "X-Diapason-User-Id": "x"}, files=files, data=data).status_code == 400
    assert client.post("/api/sessions", headers=headers).status_code == 404


def test_capture_validation_precedence(offline, headers, monkeypatch):
    client = TestClient(offline.app)
    files = {"pdf": ("bad.pdf", b"not pdf", "application/pdf")}
    assert client.post(CAPTURE_PATH, headers=headers, files=files, data={"trade_type": ""}).status_code == 422
    assert client.post(CAPTURE_PATH, headers=headers, files=files, data={"trade_type": "loan"}).status_code == 404
    monkeypatch.setitem(offline.cfg["intelligence_contract"], "enabled", True)
    assert client.post(CAPTURE_PATH, headers=headers, files=files, data={"trade_type": "loan"}).status_code == 503
    model = MagicMock()
    monkeypatch.setattr(offline.runtime, "azure_client", lambda: {"client": model, "deployment": "same"})
    response = client.post(CAPTURE_PATH, headers=headers, files=files, data={"trade_type": "loan", "session_id": "unknown"})
    assert response.status_code == 404
    response = client.post(CAPTURE_PATH, headers=headers, files=files, data={"trade_type": "loan"})
    assert response.status_code == 400
    assert response.json()["detail"] == "File is not a PDF (%PDF- header missing)"
    assert model.close.call_count == 2


def test_capture_response_scope_artifacts_and_credential_forwarding(offline, headers, monkeypatch):
    client = TestClient(offline.app)
    monkeypatch.setitem(offline.cfg["intelligence_contract"], "enabled", True)
    model = MagicMock()
    monkeypatch.setattr(offline.runtime, "azure_client", lambda: {"client": model, "deployment": "same"})
    seen = {}

    async def run(**kwargs):
        seen.update(kwargs)
        return {"success": True, "trade_xml": "<trade/>", "trade_type": kwargs["trade_type"],
                "view_entity": "loanDeposit", "menu_name": "loanDeposit", "extracted_field_count": 0,
                "warnings": [], "message": "", "tool_trace": [], "session_artifacts": {"pdf_text": "private"},
                "timings_ms": {"extract": 3, "resolve": 4}}

    monkeypatch.setattr(offline.capture_routes, "run_capture", run)
    response = client.post(CAPTURE_PATH, headers=headers, files={"pdf": ("selected.pdf", b"%PDF-content")}, data={"trade_type": " iamLoan ", "debug": "yes"})
    assert response.status_code == 200
    assert "session_artifacts" not in response.json() and "timings_ms" not in response.json()
    assert seen["trade_type"] == "iamLoan" and seen["pdf_bytes"] == b"%PDF-content" and seen["debug"] is True
    bearer = seen["cluster"].diapason.request_headers["Authorization"].removeprefix("Bearer ")
    payload = json.loads(Fernet(offline.key).decrypt(bearer.encode()))
    assert payload == {"scope": 12, "base_url": "https://company.test/diapason", "api_token": "user-specific-api-token"}
    saved = offline.sessions.appended[-1]
    assert saved[1] == "test/7/9" and saved[0] == response.headers["X-Diapason-Chat-Session"]
    assert saved[4]["skill_run"]["artifacts"] == {"pdf_text": "private"}
    assert saved[4]["skill_run"]["skill"] == "intelligence-contract"
    model.close.assert_called_once()


def test_revocation_is_enforced(offline, headers):
    token = offline.auth.mint(sub="instance:revocation-test", roles=["chat"], customer_id=7)["access_token"]
    claims = offline.auth.validate(token)
    offline.auth.revoke(jti=claims["jti"])
    assert TestClient(offline.app).get(CAPTURE_PATH, headers={**headers, "Authorization": f"Bearer {token}"}).status_code == 401
