from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.fernet import Fernet
import json

from capture.api import extraction
from capture.workflow import prompts

PATH = "/api/skills/intelligence-contract"
SESSION = "X-Diapason-Chat-Session"


@pytest.fixture
def extraction_run(service, monkeypatch):
    client = Mock()
    monkeypatch.setattr(service.runtime, "azure_client", lambda: {"client": client, "deployment": "same"})
    result = {
        "success": True, "trade_xml": "<trade/>", "trade_type": "iamLoan", "view_entity": "loanDeposit",
        "menu_name": "loanDeposit", "extracted_field_count": 3, "message": "", "warnings": [], "tool_trace": [],
        "session_artifacts": {"source_trade_xml": "private source"}, "timings_ms": {"extract": 5},
    }
    run = AsyncMock(return_value=result)
    monkeypatch.setattr(extraction, "run_capture", run)
    return run, client


def upload(service, **kwargs):
    return service.client.post(PATH, headers=kwargs.pop("headers", service.headers), data=kwargs.pop("data", {"trade_type": " iamLoan ", "debug": "yes"}), files={"pdf": ("contract.pdf", b"%PDF-exact", "application/pdf")}, **kwargs)


def test_classic_upload_persists_original_artifact_contract(service, extraction_run):
    run, client = extraction_run
    response = upload(service)
    assert response.status_code == 200
    assert "session_artifacts" not in response.json() and "timings_ms" not in response.json()
    sid = response.headers[SESSION]
    assert len(service.runtime.sessions.writes) == 1
    assert service.runtime.sessions.writes[0][:2] == (sid, service.scope)
    record = service.runtime.sessions.get_session(sid, service.scope)
    assert record["turns"][0]["content"] == "@intelligence-contract import iamLoan from contract.pdf"
    assistant = record["turns"][1]
    assert assistant["skill_run"]["skill"] == "intelligence-contract"
    assert assistant["skill_run"]["artifacts"]["source_trade_xml"] == "private source"
    kwargs = run.call_args.kwargs
    assert kwargs["trade_type"] == "iamLoan" and kwargs["debug"] is True and kwargs["pdf_bytes"] == b"%PDF-exact"
    server = kwargs["cluster"].diapason
    bearer = server.request_headers["Authorization"].removeprefix("Bearer ")
    decoded = json.loads(Fernet(service.runtime.config["mcp"]["default"]["config_key"]).decrypt(bearer.encode()))
    assert decoded == {"base_url": "https://company.example", "scope": 3, "api_token": "private-api-token"}
    client.close.assert_called_once()


@pytest.mark.parametrize("via_form", [False, True])
def test_active_session_and_scope_are_preserved(service, extraction_run, via_form):
    sid = service.runtime.sessions.create_session(service.scope)["session_id"]
    headers = {**service.headers, SESSION: sid}
    data = {"trade_type": "iamLoan"}
    if via_form:
        data["session_id"] = sid
        headers[SESSION] = "wrong-header"
    response = upload(service, headers=headers, data=data)
    assert response.status_code == 200 and response.headers[SESSION] == sid
    assert len(service.runtime.sessions.records) == 1


def test_cross_user_session_is_rejected(service, extraction_run):
    run, client = extraction_run
    sid = service.runtime.sessions.create_session("demo/7/999")["session_id"]
    response = upload(service, data={"trade_type": "iamLoan", "session_id": sid})
    assert response.status_code == 404
    run.assert_not_called()
    client.close.assert_called_once()


@pytest.mark.parametrize("mutation,status", [("token", 401), ("role", 401), ("customer", 403), ("mcp", 400), ("revoked", 401)])
def test_real_auth_rejects_before_workflow(service, extraction_run, mutation, status):
    run, _ = extraction_run
    headers = dict(service.headers)
    if mutation == "token": headers["Authorization"] = "Bearer invalid"
    if mutation == "role": headers["Authorization"] = "Bearer " + service.runtime.auth.mint(sub="demo", roles=["refresh"])["access_token"]
    if mutation == "customer": headers["X-Diapason-Customer-Id"] = "8"
    if mutation == "mcp": headers.pop("X-Diapason-Mcp-Token")
    if mutation == "revoked": service.runtime.auth.revoke(jti=service.token["jti"])
    assert upload(service, headers=headers).status_code == status
    run.assert_not_called()


@pytest.mark.parametrize("error,status", [(ValueError("bad PDF"), 400), (RuntimeError("resolver failed"), 502)])
def test_workflow_error_status_and_client_cleanup(service, extraction_run, error, status):
    run, client = extraction_run
    run.side_effect = error
    response = upload(service)
    assert response.status_code == status and response.json()["detail"] == str(error)
    assert service.runtime.sessions.writes == []
    client.close.assert_called_once()


def test_metadata_needs_only_chat_role_and_capture_has_no_chat_frontend(service, monkeypatch):
    monkeypatch.setattr(prompts, "_catalog_version", "v1")
    response = service.client.get(PATH, headers={"Authorization": service.headers["Authorization"]})
    assert response.status_code == 200 and response.json()["prompt_version"] == "v1"
    for path in ("/", "/api/chat", "/api/sessions", "/static/index.html"):
        assert service.client.get(path).status_code == 404
    assert service.client.get("/health").json()["status"] == "ok"
