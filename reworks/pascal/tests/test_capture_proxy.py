from email.parser import BytesParser
from email.policy import default
from unittest.mock import Mock

import httpx
import pytest

from pascal.integrations import capture

PATH = capture.EXTRACTION_PATH


@pytest.fixture
def upstream(monkeypatch):
    monkeypatch.setenv("CAPTURE_URL", "https://capture.example/")
    handler = Mock(return_value=httpx.Response(200, json={"enabled": True, "trade_types": ["iamLoan"]}))
    client_class = httpx.AsyncClient
    def client(**kwargs):
        return client_class(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(capture.httpx, "AsyncClient", client)
    return handler


def test_metadata_is_remote(service, upstream):
    response = service.client.get(PATH, headers=service.headers)
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "trade_types": ["iamLoan"]}
    sent = upstream.call_args.args[0]
    assert str(sent.url) == "https://capture.example" + PATH
    assert sent.headers["authorization"] == service.headers["Authorization"]


def test_upload_preserves_identity_pdf_fields_and_response_without_local_write(service, upstream):
    body = b'{"success":true,"trade_xml":"<trade/>","trade_type":"iamLoan"}'
    upstream.return_value = httpx.Response(200, content=body, headers={"content-type": "application/json", capture.CHAT_SESSION_HEADER: "active-session"})
    headers = {**service.headers, capture.CHAT_SESSION_HEADER: "header-session", "Cookie": "unrelated=private", "X-Extra": "do not forward"}
    pdf = b"%PDF-1.7\nexact bytes\x00\xff"
    response = service.client.post(PATH, headers=headers, data={"trade_type": "iamLoan", "debug": "yes", "session_id": "form-session"}, files={"pdf": ("selected.pdf", pdf, "application/pdf")})
    assert response.status_code == 200 and response.content == body
    assert response.headers[capture.CHAT_SESSION_HEADER] == "active-session"
    request = upstream.call_args.args[0]
    assert request.method == "POST"
    for key, value in service.headers.items():
        assert request.headers[key] == value
    assert request.headers[capture.CHAT_SESSION_HEADER] == "header-session"
    assert "cookie" not in request.headers and "x-extra" not in request.headers
    multipart = BytesParser(policy=default).parsebytes(b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.content)
    parts = {part.get_param("name", header="content-disposition"): part for part in multipart.iter_parts()}
    assert parts["pdf"].get_payload(decode=True) == pdf
    assert parts["pdf"].get_filename() == "selected.pdf"
    assert {key: parts[key].get_content() for key in ("trade_type", "debug", "session_id")} == {"trade_type": "iamLoan", "debug": "yes", "session_id": "form-session"}
    assert service.runtime.sessions.writes == [] and service.runtime.sessions.records == {}
    upstream.assert_called_once()


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422, 502, 503])
def test_upstream_errors_are_preserved(service, upstream, code):
    upstream.return_value = httpx.Response(code, json={"detail": "original error"})
    response = service.client.get(PATH, headers=service.headers)
    assert response.status_code == code and response.json() == {"detail": "original error"}


@pytest.mark.parametrize("exception,code", [(httpx.ReadTimeout, 504), (httpx.ConnectError, 502)])
def test_network_errors_do_not_retry_or_expose_details(service, upstream, exception, code):
    upstream.side_effect = exception("private connection details")
    response = service.client.post(PATH, headers=service.headers, data={"trade_type": "iamLoan"}, files={"pdf": ("a.pdf", b"%PDF-")})
    assert response.status_code == code
    assert "private" not in response.text
    upstream.assert_called_once()


def test_disabled_and_unconfigured_do_not_execute(service, upstream, monkeypatch):
    service.runtime.config["intelligence_contract"]["enabled"] = False
    assert service.client.get(PATH, headers=service.headers).status_code == 404
    service.runtime.config["intelligence_contract"]["enabled"] = True
    monkeypatch.delenv("CAPTURE_URL")
    assert service.client.get(PATH, headers=service.headers).status_code == 503
    upstream.assert_not_called()


@pytest.mark.parametrize("mutation,status", [("token", 401), ("customer", 403), ("user", 400), ("mcp", 400), ("revoked", 401)])
def test_company_auth_runs_before_forwarding(service, upstream, mutation, status):
    headers = dict(service.headers)
    if mutation == "token": headers["Authorization"] = "Bearer invalid"
    if mutation == "customer": headers["X-Diapason-Customer-Id"] = "8"
    if mutation == "user": headers.pop("X-Diapason-User-Id")
    if mutation == "mcp": headers.pop("X-Diapason-Mcp-Token")
    if mutation == "revoked": service.runtime.auth.revoke(jti=service.token["jti"])
    response = service.client.post(PATH, headers=headers, data={"trade_type": "iamLoan"}, files={"pdf": ("a.pdf", b"%PDF-")})
    assert response.status_code == status
    upstream.assert_not_called()


def test_refresh_keeps_role_and_nested_response(service, upstream, monkeypatch):
    from pascal.api import health
    monkeypatch.setattr(health, "refresh_system_prompt", lambda *args: {"ok": True, "version": "chat-v1"})
    upstream.return_value = httpx.Response(200, json={"ok": True, "version": "capture-v2"})
    assert service.client.post("/api/refresh-prompt", headers=service.headers).status_code == 401
    token = service.runtime.auth.mint(sub="refresh", roles=["refresh"])["access_token"]
    response = service.client.post("/api/refresh-prompt", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "version": "chat-v1", "intelligence_contract": {"ok": True, "version": "capture-v2"}}
    assert upstream.call_args.args[0].url.path == "/api/refresh-prompt"
