"""Upload boundary: forms, identity, status mapping, correlation, and cleanup."""

from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.fernet import Fernet
import json

from capture.api import extraction

PATH = "/api/capture"
SESSION = "X-Diapason-Chat-Session"


@pytest.fixture
def extraction_run(service, monkeypatch):
    client = Mock()
    monkeypatch.setattr(
        service.runtime, "azure_client", lambda: {"client": client, "deployment": "same"}
    )
    result = {
        "success": True,
        "trade_xml": "<trade/>",
        "trade_type": "iamLoan",
        "view_entity": "loanDeposit",
        "menu_name": "loanDeposit",
        "extracted_field_count": 3,
        "message": "",
        "warnings": [],
        "tool_trace": [],
        "timings_ms": {"extract": 5},
    }
    run = AsyncMock(return_value=result)
    monkeypatch.setattr(extraction, "run_capture", run)
    return run, client


def upload(service, **kwargs):
    return service.client.post(
        PATH,
        headers=kwargs.pop("headers", service.headers),
        data=kwargs.pop("data", {"trade_type": " iamLoan ", "debug": "yes"}),
        files={"pdf": ("contract.pdf", b"%PDF-exact", "application/pdf")},
        **kwargs,
    )


@pytest.mark.parametrize("path", [PATH, "/api/skills/intelligence-contract"])
def test_upload_returns_result_without_session_storage(service, extraction_run, path):
    run, client = extraction_run
    response = service.client.post(
        path,
        headers=service.headers,
        data={"trade_type": " iamLoan ", "debug": "yes"},
        files={"pdf": ("contract.pdf", b"%PDF-exact", "application/pdf")},
    )
    assert response.status_code == 200
    assert "session_artifacts" not in response.json() and "timings_ms" not in response.json()
    assert not hasattr(service.runtime, "sessions")
    kwargs = run.call_args.kwargs
    assert (
        kwargs["trade_type"] == "iamLoan"
        and kwargs["debug"] is True
        and kwargs["pdf_bytes"] == b"%PDF-exact"
    )
    server = kwargs["cluster"].diapason
    bearer = server.request_headers["Authorization"].removeprefix("Bearer ")
    decoded = json.loads(
        Fernet(service.runtime.config["mcp"]["default"]["config_key"]).decrypt(bearer.encode())
    )
    assert decoded == {
        "base_url": "https://company.example",
        "scope": 3,
        "api_token": "private-api-token",
    }
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


@pytest.mark.parametrize(
    "mutation,status",
    [("token", 401), ("role", 401), ("customer", 403), ("mcp", 400), ("revoked", 401)],
)
def test_real_auth_rejects_before_workflow(service, extraction_run, mutation, status):
    run, _ = extraction_run
    headers = dict(service.headers)
    if mutation == "token":
        headers["Authorization"] = "Bearer invalid"
    if mutation == "role":
        headers["Authorization"] = (
            "Bearer " + service.runtime.auth.mint(sub="demo", roles=["refresh"])["access_token"]
        )
    if mutation == "customer":
        headers["X-Diapason-Customer-Id"] = "8"
    if mutation == "mcp":
        headers.pop("X-Diapason-Mcp-Token")
    if mutation == "revoked":
        service.runtime.auth.revoke(jti=service.token["jti"])
    assert upload(service, headers=headers).status_code == status
    run.assert_not_called()


@pytest.mark.parametrize(
    "error,status", [(ValueError("bad PDF"), 400), (RuntimeError("resolver failed"), 502)]
)
def test_workflow_error_status_and_client_cleanup(service, extraction_run, error, status):
    run, client = extraction_run
    run.side_effect = error
    response = upload(service)
    assert response.status_code == status and response.json()["detail"] == str(error)
    client.close.assert_called_once()


@pytest.mark.parametrize(
    "debug,expected",
    [
        ("1", True),
        ("TRUE", True),
        (" yes ", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("other", False),
        (None, False),
    ],
)
def test_debug_form_parsing(service, extraction_run, debug, expected):
    run, _ = extraction_run
    data = {"trade_type": "iamLoan"}
    if debug is not None:
        data["debug"] = debug
    assert upload(service, data=data).status_code == 200
    assert run.call_args.kwargs["debug"] is expected


@pytest.mark.parametrize("path", [PATH, "/api/skills/intelligence-contract"])
def test_disabled_capture_rejects_metadata_and_upload_before_client_creation(
    service, extraction_run, monkeypatch, path
):
    service.runtime.config["capture"]["enabled"] = False
    factory = Mock()
    monkeypatch.setattr(service.runtime, "azure_client", factory)
    assert service.client.get(path, headers=service.headers).status_code == 404
    response = service.client.post(
        path,
        headers=service.headers,
        data={"trade_type": "iamLoan"},
        files={"pdf": ("contract.pdf", b"%PDF-exact", "application/pdf")},
    )
    assert response.status_code == 404
    factory.assert_not_called()
    extraction_run[0].assert_not_called()


def test_missing_azure_configuration_returns_503_without_workflow(
    service, extraction_run, monkeypatch
):
    monkeypatch.setattr(service.runtime, "azure_client", lambda: None)
    response = upload(service)
    assert response.status_code == 503
    assert response.json()["detail"] == "Azure OpenAI is not configured"
    extraction_run[0].assert_not_called()


@pytest.mark.parametrize("missing", ["pdf", "trade_type"])
def test_missing_required_form_fields_returns_422(service, extraction_run, missing):
    files = {} if missing == "pdf" else {"pdf": ("contract.pdf", b"%PDF-exact", "application/pdf")}
    data = {} if missing == "trade_type" else {"trade_type": "iamLoan"}
    response = service.client.post(PATH, headers=service.headers, data=data, files=files)
    assert response.status_code == 422
    assert any(error["loc"][-1] == missing for error in response.json()["detail"])
    extraction_run[0].assert_not_called()
    extraction_run[1].close.assert_not_called()


@pytest.mark.parametrize(
    "header,value",
    [
        ("X-Diapason-User-Id", None),
        ("X-Diapason-Customer-Id", None),
        ("X-Diapason-User-Id", "invalid"),
        ("X-Diapason-Customer-Id", "invalid"),
        ("X-Diapason-Mcp-Scope", None),
        ("X-Diapason-Mcp-Scope", "invalid"),
        ("X-Diapason-Mcp-Base-Url", None),
    ],
)
def test_invalid_identity_or_mcp_headers_stop_before_workflow(
    service, extraction_run, header, value
):
    headers = dict(service.headers)
    if value is None:
        headers.pop(header)
    else:
        headers[header] = value
    assert upload(service, headers=headers).status_code == 400
    extraction_run[0].assert_not_called()


def test_blank_form_correlation_falls_back_to_trimmed_header(service, extraction_run):
    response = upload(
        service,
        headers={**service.headers, SESSION: " header-session "},
        data={"trade_type": "iamLoan", "session_id": " "},
    )
    assert response.status_code == 200
    assert response.headers[SESSION] == "header-session"


def test_unexpected_failure_still_closes_azure_client(service, extraction_run):
    run, client = extraction_run
    run.side_effect = KeyError("unexpected")
    with pytest.raises(KeyError, match="unexpected"):
        upload(service)
    client.close.assert_called_once()


def test_resolution_failure_remains_a_200_business_result(service, extraction_run):
    run, client = extraction_run
    run.return_value = {**run.return_value, "success": False, "message": "unresolved"}
    response = upload(service)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["message"] == "unresolved"
    assert "timings_ms" not in response.json()
    assert "timings_ms" in run.return_value
    client.close.assert_called_once()
