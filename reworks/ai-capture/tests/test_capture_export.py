"""Export/auth behavior through MockTransport only; never use local API config."""

import base64
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from evals.client import ApiConfigError, CaptureClient, load_api_config
from capture.http_contract import (
    AUTHORIZATION_HEADER, CORRELATION_HEADER, CUSTOMER_ID_HEADER, DIAPASON_API_JWT_HEADER,
    DIAPASON_BASE_URL_HEADER, DIAPASON_SCOPE_HEADER, LOCALE_HEADER, USER_ID_HEADER,
)


@pytest.fixture
def api_config():
    return {"capture_url": "https://capture.example", "capture_jwt_token": "private-capture-token",
            "diapason_base_url": "https://diapason.example/root", "diapason_api_jwt_token": "private-diapason-token",
            "diapason_scope": 3, "diapason_user_id": 42, "diapason_customer_id": 7}


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "input.pdf"
    path.write_bytes(b"%PDF-1.4\nmock document\n%%EOF\n")
    return path


@pytest.fixture
def clean_config_env(monkeypatch):
    for name in ("INTEG_PLATFORM_CONFIG", "INTEG_APP_CONFIG", "SMOKE_API_CONFIG", "ACA_DEPLOY_URL", "CAPTURE_URL",
                 "M2M_CLIENT_ID", "M2M_CLIENT_SECRET", "M2M_TOKEN_URL", "REGISTRY_URL"):
        monkeypatch.delenv(name, raising=False)


def _success_body():
    return {"success": True, "trade_xml": '<trade><amount>123</amount></trade>', "debug": {"extract": {
        "trade_xml": '<trade><amount>1.23E2</amount></trade>', "trade_xml_raw": '<trade />',
        "llm_response": '```xml\n<trade />\n```', "deployment": "model-deployment", "model": "model-version",
        "temperature": 0.5, "prompt_path": "mltLoan.txt", "prompt_sha256": "abc123",
        "usage": {"input": 11, "output": 7, "total": 18, "private": "do-not-copy"},
        "secret": "do-not-copy", "pdf_text_preview": "document text",
    }}}


def test_capture_saves_exact_response_and_stage_artifacts(api_config, pdf, tmp_path, capsys):
    body = _success_body()
    raw = json.dumps(body, indent=3).encode() + b"\n\n"
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "POST" and request.url.path == "/api/capture"
        assert request.headers[AUTHORIZATION_HEADER] == "Bearer private-capture-token"
        assert request.headers[DIAPASON_API_JWT_HEADER] == "private-diapason-token"
        assert request.headers[DIAPASON_SCOPE_HEADER] == "3"
        assert request.headers[DIAPASON_BASE_URL_HEADER] == "https://diapason.example/root"
        assert request.headers[USER_ID_HEADER] == "42" and request.headers[CUSTOMER_ID_HEADER] == "7"
        assert request.headers[LOCALE_HEADER] == "en_US"
        assert request.headers[CORRELATION_HEADER] == "my-correlation"
        assert b'name="debug"\r\n\r\ntrue' in request.content
        assert b'name="trade_type"\r\n\r\niamLoan' in request.content
        assert pdf.read_bytes() in request.content
        return httpx.Response(200, content=raw)

    output = tmp_path / "capture"
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with CaptureClient(api_config, client=http) as client:
            assert requests == []
            result = client.capture(pdf, "iamLoan", output, correlation_id="my-correlation")
        assert not http.is_closed
    assert result["success"] and result["response"] == body
    assert (output / "response.json").read_bytes() == raw
    assert (output / "trade.xml").read_text() == body["trade_xml"]
    assert (output / "extracted.xml").read_text() == body["debug"]["extract"]["trade_xml"]
    assert (output / "model.xml").read_text() == '<trade />'
    assert (output / "model-response.txt").read_text() == '```xml\n<trade />\n```'
    run = json.loads((output / "run.json").read_text())
    assert run["pdf_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert run["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert run["model"] == "model-version" and run["prompt_sha256"] == "abc123"
    assert run["usage"] == {"input": 11, "output": 7, "total": 18}
    assert "response" not in run and "config" not in run
    assert "private" not in (output / "run.json").read_text()
    assert "document text" not in (output / "run.json").read_text()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("status, raw, category, artifact", [
    (400, b'{"detail":"bad PDF"}', "http", "response.json"),
    (503, b"backend unavailable", "http", "response.body"),
    (200, b'{"success":false,"message":"extraction failed"}', "business", "response.json"),
    (200, b"not JSON", "protocol", "response.body"),
    (200, b"[]", "protocol", "response.json"),
    (200, b'{"success":true}', "protocol", "response.json"),
    (200, b'{"success":true,"trade_xml":"<broken"}', "protocol", "response.json"),
])
def test_capture_failures_preserve_response(api_config, pdf, tmp_path, status, raw, category, artifact):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, content=raw))) as http:
        result = CaptureClient(api_config, client=http).capture(pdf, "iamLoan", tmp_path / "run")
    assert not result["success"] and result["status_code"] == status
    assert result["error_category"] == category
    assert (tmp_path / "run" / artifact).read_bytes() == raw
    assert json.loads((tmp_path / "run/run.json").read_text())["response_sha256"] == hashlib.sha256(raw).hexdigest()


def test_transport_failure_has_safe_metadata(api_config, pdf, tmp_path, capsys):
    def handler(request):
        raise httpx.ConnectError("private-token https://private.example?secret=value", request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = CaptureClient(api_config, client=http).capture(pdf, "iamLoan", tmp_path / "run")
    assert result["status_code"] is None and result["response"] is None
    assert result["error_category"] == "transport"
    run = (tmp_path / "run/run.json").read_text()
    assert "private-token" not in run and "private.example" not in run
    assert not (tmp_path / "run/response.json").exists()
    assert capsys.readouterr().out == ""


def test_input_and_output_validation_precede_auth(api_config, pdf, tmp_path):
    def handler(request):
        pytest.fail("No HTTP requests allowed")
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep")
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with CaptureClient(api_config, client=http) as client:
            with pytest.raises(ApiConfigError, match="already exists"):
                client.capture(pdf, "iamLoan", output)
            with pytest.raises(ApiConfigError, match="Cannot read input"):
                client.capture(tmp_path / "absent.pdf", "iamLoan", tmp_path / "absent-output")
    assert sentinel.read_text() == "keep"
    assert not (tmp_path / "absent-output").exists()


@pytest.mark.parametrize("content", [b"malformed document", b""])
def test_malformed_pdf_reaches_server_for_negative_evaluation(api_config, tmp_path, content):
    malformed = tmp_path / "bad.pdf"
    malformed.write_bytes(content)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400, json={"detail": "Invalid PDF"}))) as http:
        result = CaptureClient(api_config, client=http).capture(malformed, "iamLoan", tmp_path / "run")
    assert result["status_code"] == 400


def test_registry_m2m_and_diapason_login_are_reused(api_config, pdf, tmp_path):
    api_config.update(m2m_client_id="eval-client", m2m_client_secret="m2m-secret",
                      registry_url="https://registry.example/services.json", diapason_client_id="diapason-client",
                      diapason_client_secret="diapason-secret")
    requests = []
    def handler(request):
        requests.append(str(request.url))
        if request.url.host == "registry.example":
            return httpx.Response(200, json={"services": {"m2m": {"url": "https://m2m.example/token"}}})
        if request.url.host == "m2m.example":
            assert request.headers["Authorization"].startswith("Basic ")
            assert request.content == b"grant_type=client_credentials"
            return httpx.Response(200, json={"access_token": "granted-m2m-token"})
        if request.url.path.endswith("/api/login"):
            assert b"client_id=diapason-client" in request.content and b"client_secret=diapason-secret" in request.content
            return httpx.Response(200, content=b'<login apiToken="granted-api-token"/>')
        assert request.headers[AUTHORIZATION_HEADER] == "Bearer granted-m2m-token"
        assert request.headers[DIAPASON_API_JWT_HEADER] == "granted-api-token"
        return httpx.Response(200, json=_success_body())
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with CaptureClient(api_config, client=http) as client:
            assert requests == []
            assert client.capture(pdf, "iamLoan", tmp_path / "first")["success"]
            assert client.capture(pdf, "iamLoan", tmp_path / "second")["success"]
    assert len(requests) == 5


def test_auth_failure_does_not_become_capture_status(api_config, pdf, tmp_path):
    api_config.update(m2m_client_id="eval-client", m2m_client_secret="private-secret", m2m_token_url="https://m2m.example/token")
    def handler(request):
        assert request.url.host == "m2m.example"
        return httpx.Response(401, json={"detail": "private-secret"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = CaptureClient(api_config, client=http).capture(pdf, "iamLoan", tmp_path / "run")
    assert result["error_category"] == "authentication" and result["status_code"] is None
    assert "private-secret" not in (tmp_path / "run/run.json").read_text()


def test_credential_tokens_refresh_before_expiry_and_static_tokens_do_not(api_config, pdf, tmp_path, monkeypatch):
    from evals import client as client_module
    clock = [1000.0]
    monkeypatch.setattr(client_module.time, "time", lambda: clock[0])
    api_config.update(m2m_client_id="eval", m2m_client_secret="private-secret", m2m_token_url="https://m2m.example/token",
                      diapason_client_id="diapason", diapason_client_secret="private-diapason")
    calls = {"m2m": 0, "login": 0, "capture": 0}
    def handler(request):
        if request.url.host == "m2m.example":
            calls["m2m"] += 1
            return httpx.Response(200, json={"access_token": "opaque", "expires_in": 60})
        if request.url.path.endswith("/api/login"):
            calls["login"] += 1
            claims = base64.urlsafe_b64encode(json.dumps({"exp": clock[0] + 30}).encode()).decode().rstrip("=")
            return httpx.Response(200, content=f'<login apiToken="header.{claims}.signature"/>'.encode())
        calls["capture"] += 1
        return httpx.Response(200, json=_success_body())
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = CaptureClient(api_config, client=http)
        assert client.capture(pdf, "iamLoan", tmp_path / "first")["success"]
        clock[0] = 1040
        assert client.capture(pdf, "iamLoan", tmp_path / "second")["success"]
        assert calls == {"m2m": 1, "login": 2, "capture": 2}
        clock[0] = 1100
        assert client.capture(pdf, "iamLoan", tmp_path / "third")["success"]
        assert calls == {"m2m": 2, "login": 3, "capture": 3}
        for key in ("m2m_client_id", "m2m_client_secret", "m2m_token_url", "diapason_client_id", "diapason_client_secret"):
            api_config.pop(key)
        static = CaptureClient(api_config, client=http)
        clock[0] = 9999999
        assert static.capture(pdf, "iamLoan", tmp_path / "static")["success"]
        assert calls == {"m2m": 2, "login": 3, "capture": 4}


def test_401_invalidates_credentials_for_next_attempt_without_retry(api_config, pdf, tmp_path):
    api_config.update(m2m_client_id="eval", m2m_client_secret="private-secret", m2m_token_url="https://m2m.example/token")
    calls = {"m2m": 0, "capture": 0}
    def handler(request):
        if request.url.host == "m2m.example":
            calls["m2m"] += 1
            return httpx.Response(200, json={"access_token": "opaque", "expires_in": 3600})
        calls["capture"] += 1
        return httpx.Response(401, json={"detail": "expired"}) if calls["capture"] == 1 else httpx.Response(200, json=_success_body())
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = CaptureClient(api_config, client=http)
        first = client.capture(pdf, "iamLoan", tmp_path / "first")
        assert first["status_code"] == 401 and not first["success"]
        assert calls == {"m2m": 1, "capture": 1}
        assert client.capture(pdf, "iamLoan", tmp_path / "second")["success"]
        assert calls == {"m2m": 2, "capture": 2}


def test_metadata_filters_payloads_and_never_refreshes(api_config):
    def handler(request):
        assert request.method == "GET"
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "revision": "abc", "release": "v1", "secret": "do-not-copy"})
        assert request.url.path == "/api/capture"
        return httpx.Response(200, json={"enabled": True, "prompt_version": "v2", "trade_types": ["iamLoan"], "config": "private"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        value = CaptureClient(api_config, client=http).metadata()
    assert value == {"build": {"status": "ok", "revision": "abc", "release": "v1"},
                     "catalog": {"enabled": True, "prompt_version": "v2", "trade_types": ["iamLoan"]}}


def test_explicit_config_precedes_json_env_and_keeps_individual_overrides(tmp_path, monkeypatch, clean_config_env):
    config = tmp_path / "api.json"
    config.write_text('{"capture_url":"https://file.example","m2m_client_id":"file"}')
    monkeypatch.setenv("INTEG_PLATFORM_CONFIG", "invalid JSON deliberately ignored")
    monkeypatch.setenv("CAPTURE_URL", "https://override.example/")
    monkeypatch.setenv("M2M_CLIENT_ID", "override")
    assert load_api_config(config) == {"capture_url": "https://override.example", "m2m_client_id": "override"}


def test_config_environment_merge_and_legacy_fallback(monkeypatch, clean_config_env):
    monkeypatch.setenv("INTEG_PLATFORM_CONFIG", '{"common":1,"capture_url":"platform"}')
    monkeypatch.setenv("INTEG_APP_CONFIG", '{"capture_url":"app"}')
    monkeypatch.setenv("SMOKE_API_CONFIG", '{"capture_url":"legacy"}')
    assert load_api_config() == {"common": 1, "capture_url": "app"}
    monkeypatch.delenv("INTEG_PLATFORM_CONFIG")
    monkeypatch.delenv("INTEG_APP_CONFIG")
    assert load_api_config() == {"capture_url": "legacy"}


def test_invalid_config_uses_fixed_safe_error(tmp_path, clean_config_env):
    config = tmp_path / "api.json"
    config.write_text("private-secret-not-json")
    with pytest.raises(ApiConfigError, match="API config file: invalid JSON") as raised:
        load_api_config(config)
    assert "private-secret" not in str(raised.value)

