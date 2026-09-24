import json
from urllib.parse import parse_qs

import httpx
import pytest

from . import smoke_capture as smoke


def test_smoke_exercises_m2m_login_and_capture(tmp_path, monkeypatch, capsys):
    for env in ("EXPECTED_REVISION", "IMAGE_TAG", "RELEASE_TAG"):
        monkeypatch.delenv(env, raising=False)
    (tmp_path / "sample.pdf").write_bytes(b"%PDF-test")
    config = {
        "capture_url": "https://capture.example", "registry_url": "https://registry.example/services.json",
        "m2m_client_id": "test", "m2m_client_secret": "m2m-secret",
        "diapason_base_url": "https://diapason.example", "diapason_client_id": "test-api",
        "diapason_client_secret": "api-secret", "diapason_scope": 3,
        "diapason_user_id": 42, "diapason_customer_id": 7, "capture_pdf": "sample.pdf",
    }
    seen = []
    def handler(request):
        seen.append(request)
        if request.url.host == "registry.example":
            return httpx.Response(200, json={"services": {"m2m": {"url": "https://m2m.example/token"}}})
        if request.url.host == "m2m.example":
            assert request.headers["authorization"].startswith("Basic ")
            assert parse_qs(request.content.decode())["scope"] == ["ai-capture"]
            return httpx.Response(200, json={"access_token": "private-token"})
        if request.url.path == "/api/login":
            return httpx.Response(200, text='<login apiToken="private-api-token"/>')
        if request.url.path.endswith("health"):
            return httpx.Response(200, json={"status": "ok", "build_date": "today", "revision": "sha", "release": ""})
        if "authorization" not in request.headers:
            return httpx.Response(401, json={"detail": "unauthenticated"})
        if request.method == "POST" and request.url.path == "/api/capture":
            assert request.headers["X-Diapason-Mcp-Token"] == "private-api-token"
            assert b"%PDF-test" in request.content
            return httpx.Response(200, json={"success": True, "trade_xml": "<trade/>"},
                                  headers={smoke.CORRELATION_HEADER: "capture-smoke"})
        return httpx.Response(200, json={"enabled": True})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        smoke.run_smoke(config, tmp_path, client)
    assert len(seen) == 10
    output = capsys.readouterr().out
    assert "passed" in output and "private" not in output and "secret" not in output


def test_smoke_config_prefers_deployed_url_and_env_secrets(monkeypatch):
    monkeypatch.setenv("SMOKE_API_CONFIG", json.dumps({"capture_url": "http://old", "m2m_client_id": "old"}))
    monkeypatch.setenv("ACA_DEPLOY_URL", "https://new/")
    monkeypatch.setenv("CAPTURE_URL", "https://wrong")
    monkeypatch.setenv("M2M_CLIENT_ID", "new")
    config, base = smoke.load_config()
    assert config["capture_url"] == "https://new" and config["m2m_client_id"] == "new"
    assert base == smoke.TESTS_DIR


def test_smoke_fails_on_wrong_revision(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPECTED_REVISION", "wanted")
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        "status": "ok", "revision": "wrong", "build_date": "today", "release": "",
    }))) as client:
        with pytest.raises(ValueError, match="revision"):
            smoke.run_smoke({"capture_url": "https://capture.example"}, tmp_path, client)