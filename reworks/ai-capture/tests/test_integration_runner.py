"""Offline tests of the opt-in HTTP runner; every response uses MockTransport."""

import json
import runpy
import sys
from urllib.parse import parse_qs

import httpx
import pytest

from . import test_integ as integ


def test_importing_runner_neither_loads_config_nor_starts_live_checks(monkeypatch):
    monkeypatch.setenv("INTEG_APP_CONFIG", "invalid JSON must not be read during import")

    def unexpected_client(*args, **kwargs):
        pytest.fail("Importing the integration runner must not create a live HTTP client")

    monkeypatch.setattr(httpx, "Client", unexpected_client)
    module = runpy.run_path(str(integ.TESTS_DIR / "test_integ.py"), run_name="imported_integ")
    assert module["__test__"] is False


@pytest.fixture(autouse=True)
def clean_integration_env(monkeypatch):
    for name in (
        "INTEG_PLATFORM_CONFIG", "INTEG_APP_CONFIG", "SMOKE_API_CONFIG",
        "ACA_DEPLOY_URL", "CAPTURE_URL", "M2M_CLIENT_ID", "M2M_CLIENT_SECRET",
        "M2M_TOKEN_URL", "REGISTRY_URL", "EXPECTED_REVISION", "IMAGE_TAG", "RELEASE_TAG",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def api_config(tmp_path):
    (tmp_path / "sample.pdf").write_bytes(b"%PDF-test")
    return {
        "capture_url": "https://capture.example", "registry_url": "https://registry.example/services.json",
        "m2m_client_id": "test", "m2m_client_secret": "m2m-secret",
        "diapason_base_url": "https://diapason.example", "diapason_client_id": "test-api",
        "diapason_client_secret": "api-secret", "diapason_scope": 3,
        "diapason_user_id": 42, "diapason_customer_id": 7, "capture_pdf": "sample.pdf",
        "trade_type": "iamLoan",
    }


def capture_result():
    return {
        "success": True,
        # Resolution replaces the shortname with an ID. Check the source, not this ID.
        "trade_xml": "<trade><tradeType>123</tradeType></trade>",
        "debug": {"extract": {"trade_xml": '<trade><tradeType shortname="iamLoan"/></trade>'}},
    }


def test_command_line_runner_mints_tokens_and_checks_pdf_extraction_over_http(api_config, tmp_path, monkeypatch, capsys):
    seen = []

    def handler(request):
        seen.append((request.method, request.url.host, request.url.path))
        if request.url.host == "registry.example":
            return httpx.Response(200, json={"services": {"m2m": {"url": "https://m2m.example/token"}}})
        if request.url.host == "m2m.example":
            assert request.headers["authorization"].startswith("Basic ")
            # Match ai-agent: ask for configured client scopes, not a hardcoded scope.
            assert parse_qs(request.content.decode()) == {"grant_type": ["client_credentials"]}
            return httpx.Response(200, json={"access_token": "private-token"})
        if request.url.path == "/api/login":
            assert parse_qs(request.content.decode()) == {
                "client_id": ["test-api"], "client_secret": ["api-secret"], "locale": ["en_US"],
            }
            return httpx.Response(200, text='<login apiToken="private-api-token"/>')
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "build_date": "today", "revision": "sha", "release": ""})
        assert request.url.path == "/api/capture"
        if "authorization" not in request.headers:
            return httpx.Response(401, json={"detail": "unauthenticated"})
        assert request.headers["authorization"] == "Bearer private-token"
        if request.method == "POST":
            assert request.headers[integ.DIAPASON_API_JWT_HEADER] == "private-api-token"
            assert request.headers[integ.USER_ID_HEADER] == "42"
            assert request.headers[integ.CUSTOMER_ID_HEADER] == "7"
            assert request.headers[integ.DIAPASON_SCOPE_HEADER] == "3"
            assert request.headers[integ.DIAPASON_BASE_URL_HEADER] == "https://diapason.example"
            assert b"%PDF-test" in request.content
            assert b'name="debug"\r\n\r\ntrue' in request.content
            assert b'name="trade_type"\r\n\r\niamLoan' in request.content
            assert request.extensions["timeout"]["read"] == 600
            return httpx.Response(200, json=capture_result(), headers={integ.CORRELATION_HEADER: "capture-integ"})
        return httpx.Response(200, json={"enabled": True, "trade_types": ["iamLoan"], "prompt_version": "v1"})

    config_path = tmp_path / "api.json"
    config_path.write_text(json.dumps(api_config), encoding="utf-8")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(sys, "argv", [str(integ.TESTS_DIR / "test_integ.py"), str(config_path)])
    runpy.run_path(sys.argv[0], run_name="__main__")
    assert client.is_closed
    assert seen == [
        ("GET", "registry.example", "/services.json"),
        ("POST", "m2m.example", "/token"),
        ("GET", "capture.example", "/health"),
        ("POST", "diapason.example", "/api/login"),
        ("GET", "capture.example", "/api/capture"),
        ("GET", "capture.example", "/api/capture"),
        ("POST", "capture.example", "/api/capture"),
    ]
    output = capsys.readouterr().out
    assert "All Capture integration checks passed" in output
    assert all(value not in output for value in ("private", "secret", "<trade"))


def test_config_merges_platform_and_app_then_applies_deployment_overrides(monkeypatch):
    monkeypatch.setenv("INTEG_PLATFORM_CONFIG", json.dumps({"capture_url": "http://old", "m2m_client_id": "platform"}))
    monkeypatch.setenv("INTEG_APP_CONFIG", json.dumps({"m2m_client_id": "app", "diapason_scope": 3}))
    monkeypatch.setenv("SMOKE_API_CONFIG", json.dumps({"capture_url": "http://legacy"}))
    monkeypatch.setenv("ACA_DEPLOY_URL", "https://deployed/")
    monkeypatch.setenv("CAPTURE_URL", "https://wrong")
    monkeypatch.setenv("M2M_CLIENT_SECRET", "env-secret")
    config, base = integ.load_config()
    assert config == {"capture_url": "https://deployed", "m2m_client_id": "app", "diapason_scope": 3,
                      "m2m_client_secret": "env-secret"}
    assert base == integ.TESTS_DIR


def test_config_accepts_legacy_blob_and_env_credentials(monkeypatch):
    monkeypatch.setenv("SMOKE_API_CONFIG", json.dumps({"capture_url": "http://old", "m2m_client_id": "old"}))
    monkeypatch.setenv("CAPTURE_URL", "https://new/")
    monkeypatch.setenv("M2M_CLIENT_ID", "new")
    config, base = integ.load_config()
    assert config == {"capture_url": "https://new", "m2m_client_id": "new"}
    assert base == integ.TESTS_DIR


def test_config_file_resolves_pdf_relative_to_file(tmp_path):
    folder = tmp_path / "config"
    folder.mkdir()
    (folder / "loan.pdf").write_bytes(b"%PDF-test")
    path = folder / "api.json"
    path.write_text(json.dumps({"capture_pdf": "loan.pdf"}), encoding="utf-8")
    config, base = integ.load_config(path)
    assert integ._pdf_path(config, base) == folder / "loan.pdf"


@pytest.mark.parametrize("config", [
    {},
    {"capture_pdf": "tests/fixtures/sample-loan-contract.pdf"},
    {"intelligence_contract_pdf": "test/fixtures/sample-loan-contract.pdf"},
])
def test_pdf_default_and_migrated_ai_agent_path(config, tmp_path):
    assert integ._pdf_path(config, tmp_path).resolve() == integ.TESTS_DIR / "fixtures/sample-loan-contract.pdf"


def test_missing_pdf_fails_before_any_network_request(api_config, tmp_path):
    api_config["capture_pdf"] = "missing.pdf"

    def handler(request):
        pytest.fail("Missing local input must be reported before making a request")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(integ.IntegrationFailure, match="Missing capture_pdf"):
            integ.run_integration(api_config, tmp_path, client)


def test_static_tokens_require_no_login():
    def handler(request):
        pytest.fail("Static credentials should not contact token endpoints")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert integ._capture_token({"capture_jwt_token": "capture-token"}, client) == "capture-token"
        assert integ._diapason_token({"diapason_api_jwt_token": "api-token"}, client) == "api-token"


def test_diapason_login_accepts_ai_agent_credential_aliases():
    def handler(request):
        assert parse_qs(request.content.decode())["client_id"] == ["legacy-client"]
        return httpx.Response(200, text='<login token="api-token"/>')

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert integ._diapason_token({"diapason_base_url": "https://diapason.example",
                                      "client_id": "legacy-client", "client_secret": "secret"}, client) == "api-token"


@pytest.mark.parametrize("env,expected", [("IMAGE_TAG", "revision"), ("EXPECTED_REVISION", "revision"), ("RELEASE_TAG", "release")])
def test_health_rejects_wrong_deployment_identity(monkeypatch, env, expected):
    monkeypatch.setenv(env, "wanted")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "status": "ok", "revision": "wrong", "build_date": "today", "release": "",
    }))) as client:
        with pytest.raises(integ.IntegrationFailure, match=expected):
            integ.check_health(client, "https://capture.example")


def test_health_falls_back_to_api_health():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(404) if request.url.path == "/health" else httpx.Response(200, json={
            "status": "ok", "revision": "dev", "build_date": "", "release": "",
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        integ.check_health(client, "https://capture.example")
    assert seen == ["/health", "/api/health"]


@pytest.mark.parametrize("mutation,message", [
    ({"success": False}, "resolved XML"),
    ({"trade_xml": "<trade/>"}, "no tradeType"),
    ({"debug": {}}, "missing source"),
    ({"debug": {"extract": {"trade_xml": '<trade><tradeType shortname="wrong"/></trade>'}}}, "requested trade_type"),
])
def test_capture_assertions_detect_failed_workflow_or_wrong_trade_type(mutation, message):
    with pytest.raises(integ.IntegrationFailure, match=message):
        integ.check_capture_result({**capture_result(), **mutation}, "iamLoan")


def test_config_and_response_errors_do_not_print_secret_values(monkeypatch):
    monkeypatch.setenv("INTEG_APP_CONFIG", '{"secret": "private-secret", BAD}')
    with pytest.raises(SystemExit) as caught:
        integ.main([])
    assert str(caught.value) == "INTEG_APP_CONFIG: invalid JSON"
    with pytest.raises(integ.IntegrationFailure) as caught:
        integ.check(httpx.Response(500, text="private-secret"), "POST /api/capture")
    assert str(caught.value) == "POST /api/capture: HTTP 500, expected 200"
