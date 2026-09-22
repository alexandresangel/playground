"""Exercise smoke authentication and the installed service over real local HTTP."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs

from cryptography.fernet import Fernet
import httpx
import pytest

spec = importlib.util.spec_from_file_location("smoke_capture", Path(__file__).with_name("smoke_capture.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_client_credentials_uses_basic_auth_and_no_scope():
    def handler(request):
        assert request.headers["Authorization"] == "Basic Y2xpZW50OnNlY3JldA=="
        assert parse_qs(request.content.decode()) == {"grant_type": ["client_credentials"]}
        return httpx.Response(200, json={"access_token": "test-token"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert smoke.access_token({"m2m_token_url": "https://m2m.example/token",
                                   "m2m_client_id": "client", "m2m_client_secret": "secret"}, client) == "test-token"


def test_static_token_does_not_call_m2m():
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("unexpected network call"))) as client:
        assert smoke.access_token({"capture_access_token": "static"}, client) == "static"


def test_auth_failure_does_not_echo_credentials_or_response_body():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text="private-secret"))) as client:
        with pytest.raises(RuntimeError, match="M2M token: HTTP 401") as error:
            smoke.access_token({"m2m_token_url": "https://m2m.example/token",
                                "m2m_client_id": "client", "m2m_client_secret": "private-secret"}, client)
    assert "private-secret" not in str(error.value)


def test_real_http_startup_auth_and_extraction(tmp_path, m2m_keys, mint_token, monkeypatch):
    requests = []

    class Platform(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body, content_type="application/json"):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(body.encode())

        def do_GET(self):
            requests.append(self.path)
            if self.path == "/services.json":
                self.send(json.dumps({"services": {"m2m": {"url": issuer + "/token"}}}))
            elif self.path == "/.well-known/jwks.json":
                self.send(json.dumps({"keys": [m2m_keys[1]]}))
            else:
                self.send_error(404)

        def do_POST(self):
            requests.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.path == "/token":
                self.send(json.dumps({"access_token": mint_token(iss=issuer)}))
            elif self.path == "/api/login":
                self.send('<login apiToken="test-diapason"/>', "application/xml")
            else:
                self.send_error(404)

    platform = ThreadingHTTPServer(("127.0.0.1", 0), Platform)
    issuer = f"http://127.0.0.1:{platform.server_port}"
    thread = threading.Thread(target=platform.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[1]
    config = {
        "registry_url": issuer + "/services.json", "m2m": {"allow_http": True},
        "capture": {"enabled": True},
        "azure_openai": {"endpoint": "https://offline.example", "api_key": "test", "deployment": "test"},
        "mcp": {"default": {"server_url": "https://offline.example/mcp", "config_key": Fernet.generate_key().decode()}},
    }
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OTEL_", "LANGSMITH_", "LANGCHAIN_"))}
    env.update(CHAT_CONFIG=json.dumps(config), PORT=str(port), PYTHONUNBUFFERED="1")
    for key in ("EXPECTED_VERSION", "EXPECTED_REVISION"):
        monkeypatch.delenv(key, raising=False)
    base = f"http://127.0.0.1:{port}"
    process = None
    try:
        with (tmp_path / "service.log").open("w+") as log:
            process = subprocess.Popen([sys.executable, str(root / "tests/container_bootstrap.py")], cwd=root,
                                       env=env, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 20
            with httpx.Client(timeout=5, trust_env=False) as client:
                while True:
                    try:
                        if client.get(base + "/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if process.poll() is not None or time.monotonic() >= deadline:
                        log.seek(0)
                        pytest.fail("Service failed to start: " + log.read())
                    time.sleep(0.1)
                smoke.run_smoke({
                    "capture_url": base, "registry_url": issuer + "/services.json",
                    "m2m_client_id": "test", "m2m_client_secret": "test",
                    "diapason_base_url": issuer, "diapason_client_id": "test", "diapason_client_secret": "test",
                    "diapason_user_id": 42, "diapason_customer_id": 7, "diapason_scope": 3,
                    "capture_pdf": "fixtures/sample-loan-contract.pdf", "trade_type": "iamLoan",
                }, client, root / "tests")
        assert requests.count("/services.json") == 2  # service startup and smoke token discovery
        assert "/.well-known/jwks.json" in requests
        assert "/token" in requests and "/api/login" in requests
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=10)
        platform.shutdown()
        platform.server_close()
        thread.join(timeout=5)
