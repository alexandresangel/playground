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
        "timings_ms": {"extract": 5},
    }
    run = AsyncMock(return_value=result)
    monkeypatch.setattr(extraction, "run_capture", run)
    return run, client


def upload(service, **kwargs):
    return service.client.post(PATH, headers=kwargs.pop("headers", service.headers), data=kwargs.pop("data", {"trade_type": " iamLoan ", "debug": "yes"}), files={"pdf": ("contract.pdf", b"%PDF-exact", "application/pdf")}, **kwargs)


@pytest.mark.parametrize("path", [PATH, "/api/capture"])
def test_upload_returns_result_without_session_storage(service, extraction_run, path):
    run, client = extraction_run
    response = service.client.post(path, headers=service.headers, data={"trade_type": " iamLoan ", "debug": "yes"}, files={"pdf": ("contract.pdf", b"%PDF-exact", "application/pdf")})
    assert response.status_code == 200
    assert "session_artifacts" not in response.json() and "timings_ms" not in response.json()
    assert not hasattr(service.runtime, "sessions")
    kwargs = run.call_args.kwargs
    assert kwargs["trade_type"] == "iamLoan" and kwargs["debug"] is True and kwargs["pdf_bytes"] == b"%PDF-exact"
    server = kwargs["cluster"].diapason
    bearer = server.request_headers["Authorization"].removeprefix("Bearer ")
    decoded = json.loads(Fernet(service.runtime.config["mcp"]["default"]["config_key"]).decrypt(bearer.encode()))
    assert decoded == {"base_url": "https://company.example", "scope": 3, "api_token": "private-api-token"}
    client.close.assert_called_once()


@pytest.mark.parametrize("via_form", [False, True])
def test_pascal_correlation_id_is_preserved_without_lookup(service, extraction_run, via_form):
    sid = "pascal-session-42"
    headers = {**service.headers, SESSION: sid}
    data = {"trade_type": "iamLoan"}
    if via_form:
        data["session_id"] = sid
        headers[SESSION] = "wrong-header"
    response = upload(service, headers=headers, data=data)
    assert response.status_code == 200 and response.headers[SESSION] == sid


def test_requests_without_correlation_get_independent_ids(service, extraction_run):
    run, client = extraction_run
    first = upload(service)
    second = upload(service)
    assert first.status_code == second.status_code == 200
    assert first.headers[SESSION] != second.headers[SESSION]
    assert run.call_count == client.close.call_count == 2


@pytest.mark.parametrize("mutation,status", [("token", 401), ("scope", 401), ("customer", 400), ("mcp", 400), ("issuer", 401), ("expired", 401), ("missing", 401)])
def test_real_auth_rejects_before_workflow(service, extraction_run, mutation, status):
    run, _ = extraction_run
    headers = dict(service.headers)
    if mutation == "token": headers["Authorization"] = "Bearer invalid"
    if mutation == "scope": headers["Authorization"] = "Bearer " + service.mint_token(scope="ai-agent")
    if mutation == "customer": headers["X-Diapason-Customer-Id"] = "not-an-integer"
    if mutation == "mcp": headers.pop("X-Diapason-Mcp-Token")
    if mutation == "issuer": headers["Authorization"] = "Bearer " + service.mint_token(iss="https://wrong.example")
    if mutation == "expired": headers["Authorization"] = "Bearer " + service.mint_token(exp=1)
    if mutation == "missing": headers.pop("Authorization")
    assert upload(service, headers=headers).status_code == status
    run.assert_not_called()


@pytest.mark.parametrize("error,status", [(ValueError("bad PDF"), 400), (RuntimeError("resolver failed"), 502)])
def test_workflow_error_status_and_client_cleanup(service, extraction_run, error, status):
    run, client = extraction_run
    run.side_effect = error
    response = upload(service)
    assert response.status_code == status and response.json()["detail"] == str(error)
    client.close.assert_called_once()


def test_metadata_needs_only_capture_scope_and_capture_has_no_chat_frontend(service, monkeypatch):
    monkeypatch.setattr(prompts, "_catalog_version", "v1")
    response = service.client.get(PATH, headers={"Authorization": service.headers["Authorization"]})
    assert response.status_code == 200 and response.json()["prompt_version"] == "v1"
    for path in ("/", "/api/chat", "/api/sessions", "/static/index.html"):
        assert service.client.get(path).status_code == 404
    assert service.client.get("/health").json()["status"] == "ok"


def test_token_administration_is_owned_by_m2m(service):
    for path in ("/api/auth/tokens", "/api/auth/revoke"):
        assert service.client.post(path, headers=service.headers, json={}).status_code == 404


def test_m2m_identity_uses_client_id_and_proxy_tenant_headers(service, extraction_run, monkeypatch):
    record = Mock()
    monkeypatch.setattr(extraction, "record_capture_result", record)
    headers = {**service.headers, "X-Diapason-Customer-Id": "8",
               "Authorization": "Bearer " + service.mint_token(client_id="capture/client")}
    assert upload(service, headers=headers).status_code == 200
    identity = record.call_args.kwargs["identity"]
    assert identity.scope_path == "capture_client/8/42"