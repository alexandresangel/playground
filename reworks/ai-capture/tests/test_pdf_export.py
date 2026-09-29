"""The standalone PDF exporter uses mock HTTP only, never local API config."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import httpx
import pytest

from capture.http_contract import (
    AUTHORIZATION_HEADER, CORRELATION_HEADER, CUSTOMER_ID_HEADER,
    DIAPASON_API_JWT_HEADER, DIAPASON_BASE_URL_HEADER, DIAPASON_SCOPE_HEADER,
    LOCALE_HEADER, USER_ID_HEADER,
)

_SPEC = importlib.util.spec_from_file_location(
    "pdf_export_script", Path(__file__).resolve().parents[1] / "scripts/capture_pdf.py",
)
exporter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(exporter)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "INTEG_PLATFORM_CONFIG", "INTEG_APP_CONFIG", "SMOKE_API_CONFIG", "ACA_DEPLOY_URL",
        "CAPTURE_URL", "M2M_CLIENT_ID", "M2M_CLIENT_SECRET", "M2M_TOKEN_URL", "REGISTRY_URL",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def config(tmp_path):
    pdf = tmp_path / "contract.pdf"
    pdf.write_bytes(b"%PDF-1.4\nmock PDF\n%%EOF\n")
    return {
        "capture_url": "https://capture.example", "capture_jwt_token": "private-capture-token",
        "diapason_base_url": "https://diapason.example/root", "diapason_api_jwt_token": "private-diapason-token",
        "diapason_scope": 3, "diapason_user_id": 42, "diapason_customer_id": 7,
        "trade_type": "iamLoan", "capture_pdf": str(pdf),
    }


def _body():
    return {"success": True, "trade_xml": '<trade><tradeType shortname="iamLoan"/><amount>123</amount></trade>',
            "debug": {"extract": {"trade_xml": '<trade><amount>1.23E2</amount></trade>',
                                  "trade_xml_raw": '<trade />', "llm_response": "```xml\n<trade />\n```",
                                  "prompt_sha256": "abc123", "model": "model-version",
                                  "usage": {"input": 11, "output": 7, "private": "omit"},
                                  "secret": "do-not-copy", "pdf_text_preview": "document content"}}}


def test_export_only_posts_capture_and_saves_exact_artifacts(config, tmp_path):
    body = _body()
    raw = json.dumps(body, indent=3).encode() + b"\n\n"
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "POST" and request.url.path == "/api/capture"
        return httpx.Response(200, content=raw)
    output = tmp_path / "export"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert exporter.run_export(config, tmp_path, client, output_dir=output, capture_timeout_s=42) == output
    assert len(requests) == 1
    posted = requests[0]
    assert posted.headers[AUTHORIZATION_HEADER] == "Bearer private-capture-token"
    assert posted.headers[DIAPASON_API_JWT_HEADER] == "private-diapason-token"
    assert posted.headers[DIAPASON_SCOPE_HEADER] == "3"
    assert posted.headers[DIAPASON_BASE_URL_HEADER] == config["diapason_base_url"]
    assert posted.headers[USER_ID_HEADER] == "42" and posted.headers[CUSTOMER_ID_HEADER] == "7"
    assert posted.headers[LOCALE_HEADER] == "en_US" and posted.headers["Accept"] == "application/json"
    assert posted.extensions["timeout"]["read"] == 42
    assert b'name="trade_type"\r\n\r\niamLoan' in posted.content
    assert b'name="debug"\r\n\r\ntrue' in posted.content
    pdf_bytes = Path(config["capture_pdf"]).read_bytes()
    assert pdf_bytes in posted.content
    assert (output / "response.json").read_bytes() == raw
    assert (output / "trade.xml").read_text() == body["trade_xml"]
    for artifact, key in (("extracted.xml", "trade_xml"), ("model.xml", "trade_xml_raw"),
                          ("model-response.txt", "llm_response")):
        assert (output / artifact).read_text() == body["debug"]["extract"][key]
    metadata_text = (output / "run.json").read_text()
    metadata = json.loads(metadata_text)
    assert metadata["pdf_sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
    assert metadata["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert metadata["status_code"] == 200 and metadata["success"] is True
    assert metadata["correlation_id"] == posted.headers[CORRELATION_HEADER]
    assert metadata["trade_type"] == "iamLoan" and metadata["duration_seconds"] >= 0
    assert metadata["usage"] == {"input": 11, "output": 7}
    assert metadata["model"] == "model-version" and metadata["prompt_sha256"] == "abc123"
    assert "private" not in metadata_text and "document content" not in metadata_text
    assert "config" not in metadata and "response" not in metadata


@pytest.mark.parametrize("status, raw, filename, category", [
    (503, b"upstream unavailable", "response.body", "http"),
    (400, b'{"detail":"invalid PDF"}', "response.json", "http"),
    (200, b'{"success":false,"message":"extraction failed"}', "response.json", "business"),
    (200, b"not JSON", "response.body", "protocol"),
    (200, b"[]", "response.json", "protocol"),
    (200, b'{"success":true}', "response.json", "protocol"),
    (200, b'{"success":true,"trade_xml":"<broken"}', "response.json", "protocol"),
])
def test_failed_responses_preserve_original_bytes(config, tmp_path, status, raw, filename, category):
    output = tmp_path / "failed"
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, content=raw))) as client:
        with pytest.raises(exporter.ExportFailure):
            exporter.run_export(config, tmp_path, client, output_dir=output)
    assert (output / filename).read_bytes() == raw
    run = json.loads((output / "run.json").read_text())
    assert run["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert run["success"] is False and run["status_code"] == status
    assert run["error"] and run["error_category"] == category


def test_transport_error_only_saves_safe_metadata(config, tmp_path):
    def fail(request):
        raise httpx.ConnectError("private-token https://private.example?secret=value", request=request)
    output = tmp_path / "failed"
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(httpx.ConnectError):
            exporter.run_export(config, tmp_path, client, output_dir=output)
    text = (output / "run.json").read_text()
    run = json.loads(text)
    assert run["status_code"] is None and run["success"] is False
    assert run["error_category"] == "transport"
    assert "private-token" not in text and "private.example" not in text
    assert not (output / "response.json").exists()


def test_input_and_output_fail_before_authentication(config, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep")
    def no_requests(request):
        pytest.fail("No network access allowed before input validation")
    with httpx.Client(transport=httpx.MockTransport(no_requests)) as client:
        with pytest.raises(exporter.ExportFailure, match="already exists"):
            exporter.run_export(config, tmp_path, client, output_dir=output)
        config["capture_pdf"] = str(tmp_path / "absent.pdf")
        with pytest.raises(exporter.ExportFailure, match="Missing capture_pdf"):
            exporter.run_export(config, tmp_path, client, output_dir=tmp_path / "absent")
    assert (output / "keep.txt").read_text() == "keep"
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("explicit_token_url, login_aliases", [(False, False), (True, True)])
def test_known_registry_m2m_and_login_authentication(config, tmp_path, explicit_token_url, login_aliases):
    config.update(m2m_client_id="eval-client", m2m_client_secret="private-secret",
                  registry_url="https://registry.example/services.json")
    prefix = "" if login_aliases else "diapason_"
    config[prefix + "client_id"] = "diapason-client"
    config[prefix + "client_secret"] = "private-diapason"
    if explicit_token_url:
        config["m2m_token_url"] = "https://m2m.example/token"
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.host == "registry.example":
            assert request.method == "GET"
            return httpx.Response(200, json={"services": {"m2m": {"url": "https://m2m.example/token"}}})
        if request.url.host == "m2m.example":
            basic = base64.b64encode(b"eval-client:private-secret").decode()
            assert request.headers["Authorization"] == "Basic " + basic
            assert request.content == b"grant_type=client_credentials"
            assert request.headers["Accept"] == "application/json"
            return httpx.Response(200, json={"access_token": "granted-m2m-token"})
        if request.url.path == "/root/api/login":
            assert request.content == b"client_id=diapason-client&client_secret=private-diapason&locale=en_US"
            return httpx.Response(200, content=b'<login apiToken="granted-api-token"/>')
        assert request.url.path == "/api/capture" and request.method == "POST"
        assert request.headers[AUTHORIZATION_HEADER] == "Bearer granted-m2m-token"
        assert request.headers[DIAPASON_API_JWT_HEADER] == "granted-api-token"
        return httpx.Response(200, json=_body())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        exporter.run_export(config, tmp_path, client, output_dir=tmp_path / "export")
    assert len(requests) == (3 if explicit_token_url else 4)


def test_env_only_cli_uses_config_pdf_type_and_unique_default_output(config, tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "TESTS_DIR", tmp_path)
    monkeypatch.setattr(exporter, "RESPONSES_DIR", tmp_path / "responses")
    monkeypatch.setenv("INTEG_PLATFORM_CONFIG", json.dumps({**config, "trade_type": "wrong"}))
    monkeypatch.setenv("INTEG_APP_CONFIG", json.dumps({"capture_pdf": "contract.pdf", "trade_type": "iamLoan"}))
    monkeypatch.setenv("SMOKE_API_CONFIG", "invalid JSON deliberately ignored")
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_body())
    real_client = httpx.Client
    def mocked_client(**kwargs):
        assert kwargs == {"timeout": 60.0, "follow_redirects": False}
        return real_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(exporter.httpx, "Client", mocked_client)
    assert exporter.main([]) == 0
    assert exporter.main([]) == 0
    outputs = list((tmp_path / "responses").iterdir())
    assert len(outputs) == 2
    for output in outputs:
        assert re.fullmatch(r"contract-\d{8}T\d{6}Z-[0-9a-f]{8}", output.name)
        assert (output / "trade.xml").exists()
    assert len(requests) == 2
    assert all(b'name="trade_type"\r\n\r\niamLoan' in request.content for request in requests)


@pytest.mark.parametrize("config_flag", [False, True])
def test_cli_file_config_and_cwd_pdf_override(config, tmp_path, monkeypatch, config_flag):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "api.json"
    config.update(capture_pdf="absent.pdf", trade_type="wrong")
    config_path.write_text(json.dumps(config))
    monkeypatch.chdir(tmp_path)
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_body())
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(exporter.httpx, "Client", lambda **kwargs: client)
    args = (["--config"] if config_flag else []) + [str(config_path)]
    assert exporter.main(args + ["--pdf", "contract.pdf", "--trade-type", "iamLoan",
                                 "--output", "export", "--timeout", "42"]) == 0
    assert (tmp_path / "export/response.json").exists()
    assert requests[0].extensions["timeout"]["read"] == 42
    assert b'name="trade_type"\r\n\r\niamLoan' in requests[0].content


def test_config_precedence_relative_pdf_and_individual_overrides(config, tmp_path, monkeypatch):
    config_path = tmp_path / "api.json"
    config_path.write_text(json.dumps({**config, "capture_pdf": "contract.pdf"}))
    loaded, base = exporter.load_config(config_path)
    assert base == tmp_path and exporter._pdf_path(loaded, base) == tmp_path / "contract.pdf"
    monkeypatch.setenv("SMOKE_API_CONFIG", '{"capture_url":"legacy"}')
    assert exporter.load_config(config_path)[0]["capture_url"] == "legacy"
    monkeypatch.setenv("INTEG_PLATFORM_CONFIG", '{"capture_url":"platform","shared":true}')
    monkeypatch.setenv("INTEG_APP_CONFIG", '{"capture_url":"app"}')
    assert exporter.load_config(config_path)[0] == {"capture_url": "app", "shared": True}
    monkeypatch.setenv("CAPTURE_URL", "https://capture-override.example/")
    monkeypatch.setenv("ACA_DEPLOY_URL", "https://deployed.example/")
    monkeypatch.setenv("M2M_CLIENT_ID", "override-id")
    loaded, base = exporter.load_config(config_path)
    assert loaded["capture_url"] == "https://deployed.example" and loaded["m2m_client_id"] == "override-id"
    assert base == exporter.TESTS_DIR


def test_failed_cli_returns_one_and_retains_response(config, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INTEG_APP_CONFIG", json.dumps(config))
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503, content=b"unavailable")))
    monkeypatch.setattr(exporter.httpx, "Client", lambda **kwargs: client)
    assert exporter.main(["--output", str(tmp_path / "failed")]) == 1
    assert (tmp_path / "failed/response.body").read_bytes() == b"unavailable"
    assert "HTTP 503" in capsys.readouterr().err


def test_invalid_config_is_safe_and_does_not_open_http_client(monkeypatch, capsys):
    monkeypatch.setenv("INTEG_APP_CONFIG", "private-secret-invalid-json")
    def no_client(**kwargs):
        pytest.fail("Invalid config should fail before client creation")
    monkeypatch.setattr(exporter.httpx, "Client", no_client)
    assert exporter.main([]) == 1
    error = capsys.readouterr().err
    assert "invalid JSON" in error and "private-secret" not in error
