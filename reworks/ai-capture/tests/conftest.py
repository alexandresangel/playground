from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json
import time

import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

import settings
from auth_m2m import M2MAuth, m2m_deps
from capture.application import create_app
from capture.runtime import Runtime
from capture.workflow import graph, prompts
from mcp_context import McpCluster, McpServerContext


@pytest.fixture
def workflow(monkeypatch):
    """Run the real PDF/LangGraph pipeline with only model and resolver calls faked."""
    catalog = Path(__file__).resolve().parents[1] / "config/catalog.json"
    monkeypatch.setattr(prompts, "_catalog", json.loads(catalog.read_text(encoding="utf-8")))
    monkeypatch.setattr(prompts, "_prompt_cache", {})
    monkeypatch.setattr(prompts, "_catalog_version", "")
    monkeypatch.setattr(prompts, "_config_dir", catalog.parent)
    completion = Mock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='```xml\n<trade><tradeType shortname="wrong"/><amount>123</amount></trade>\n```'))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    ))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion)))
    resolver = Mock(return_value={
        "success": True,
        "trade_xml": '<trade><tradeType shortname="iamLoan"/><amount>123</amount></trade>',
        "warnings": ["review"],
    })
    monkeypatch.setattr(graph, "mcp_call_tool_json", resolver)
    cluster = McpCluster((McpServerContext("default", "Diapason", "https://mcp.example", {"Authorization": "caller"}),))
    return SimpleNamespace(
        config={"capture": {"temperature": 0.5}}, cluster=cluster,
        azure={"client": client, "deployment": "same-model"},
        completion=completion, resolver=resolver,
    )


@pytest.fixture(scope="session")
def m2m_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="capture-test", alg="RS256", use="sig")
    return key, jwk


@pytest.fixture
def mint_token(m2m_keys):
    def mint(**overrides):
        now = int(time.time())
        claims = {"iss": "https://m2m.example", "iat": now, "exp": now + 900,
                  "client_id": "demo", "scope": "ai-capture"}
        claims.update(overrides)
        return jwt.encode(claims, m2m_keys[0], algorithm="RS256", headers={"kid": "capture-test"})
    return mint


@pytest.fixture
def service(monkeypatch, m2m_keys, mint_token):
    http = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"keys": [m2m_keys[1]]})))
    auth = M2MAuth(issuer="https://m2m.example", http_client=http)
    config = {
        "capture": {"enabled": True},
        "mcp": {"default": {"server_url": "https://mcp.example/mcp", "config_key": Fernet.generate_key().decode()}},
    }
    monkeypatch.setattr(settings, "_config", config)
    deps = m2m_deps(auth)
    runtime = Runtime(Path(__file__).resolve().parents[1], config, auth, **deps)
    app = create_app(runtime.base_dir, runtime=runtime)
    token = mint_token()
    headers = {
        "Authorization": "Bearer " + token,
        "X-Diapason-User-Id": "42", "X-Diapason-Customer-Id": "7",
        "X-Diapason-Mcp-Token": "private-api-token", "X-Diapason-Mcp-Scope": "3",
        "X-Diapason-Mcp-Base-Url": "https://company.example", "X-Diapason-Locale": "fr_FR",
    }
    with http, TestClient(app) as client:
        yield SimpleNamespace(runtime=runtime, app=app, client=client, headers=headers, token=token,
                              mint_token=mint_token, scope="demo/7/42")
