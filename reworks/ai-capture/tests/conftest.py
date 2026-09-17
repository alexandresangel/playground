"""Offline fixtures shared by Capture's graph and HTTP tests."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import settings
from dia_jwt import JwtAuth
from dia_jwt.fastapi import jwt_deps
from capture.application import create_app
from capture.runtime import Runtime
from capture.workflow import graph, prompts
from mcp_context import McpCluster, McpServerContext


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_catalog(monkeypatch):
    """Each test starts with bundled config, never a previous test's cache."""
    monkeypatch.setattr(prompts, "_config_dir", PROJECT_ROOT / "config")
    monkeypatch.setattr(prompts, "_catalog", {})
    monkeypatch.setattr(prompts, "_catalog_version", "")
    monkeypatch.setattr(prompts, "_catalog_source", "")
    monkeypatch.setattr(prompts, "_prompt_cache", {})
    prompts.init_capture_prompts({}, PROJECT_ROOT)


@pytest.fixture(autouse=True)
def offline_http(monkeypatch):
    """Fail accidental HTTP calls; ASGI and explicit MockTransport still work."""

    def unexpected_request(*args, **kwargs):
        pytest.fail("Unexpected external HTTP request: use an offline transport or double")

    async def unexpected_async_request(*args, **kwargs):
        unexpected_request()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", unexpected_request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", unexpected_async_request)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


@pytest.fixture
def pdf_bytes():
    return (PROJECT_ROOT / "tests/fixtures/sample-loan-contract.pdf").read_bytes()


@pytest.fixture
def local_config(tmp_path):
    root = tmp_path / "config"
    (root / "prompts").mkdir(parents=True)
    (root / "catalog.json").write_text(
        json.dumps(
            {
                "version": "local-1",
                "prompts": {"prompts/extract.txt": ["loan"]},
            }
        ),
        encoding="utf-8",
    )
    (root / "prompts/extract.txt").write_text("Extract the contract", encoding="utf-8")
    return root


@pytest.fixture
def workflow(monkeypatch, pdf_bytes):
    """Real graph, catalog, PDF reader and XML; doubles only at remote calls."""
    completion = Mock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '```xml\n<trade><tradeType shortname="wrong"/><amount>123</amount></trade>\n```'
                        )
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
        )
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=completion)), close=Mock()
    )
    resolver = Mock(
        return_value={
            "success": True,
            "trade_xml": '<trade><tradeType shortname="iamLoan"/><amount>123</amount></trade>',
            "warnings": ["review"],
        }
    )
    monkeypatch.setattr(graph, "mcp_call_tool_json", resolver)
    context = SimpleNamespace(
        config={"capture": {"temperature": 0.5}},
        cluster=McpCluster(
            (
                McpServerContext(
                    "default", "Diapason", "https://mcp.example", {"Authorization": "caller"}
                ),
            )
        ),
        azure={"client": client, "deployment": "same-model"},
        completion=completion,
        resolver=resolver,
        pdf_bytes=pdf_bytes,
    )

    async def run(**overrides):
        arguments = dict(
            pdf_bytes=pdf_bytes,
            trade_type="iamLoan",
            cluster=context.cluster,
            config=context.config,
            azure=context.azure,
        )
        arguments.update(overrides)
        return await graph.run_capture(**arguments)

    context.run = run
    return context


@pytest.fixture
def service(tmp_path, monkeypatch):
    auth = JwtAuth.create_keystore(
        tmp_path / "key.p12", "offline-test", revocation_path=tmp_path / "revoked.json"
    )
    config = {
        "capture": {"enabled": True},
        "mcp": {
            "default": {
                "server_url": "https://mcp.example/mcp",
                "config_key": Fernet.generate_key().decode(),
            }
        },
    }
    monkeypatch.setattr(settings, "_config", config)
    deps = jwt_deps(auth)
    runtime = Runtime(Path(__file__).resolve().parents[1], config, auth, **deps)
    app = create_app(runtime.base_dir, runtime=runtime)
    token = auth.mint(sub="instance:demo", roles=["chat"], customer_id=7)
    headers = {
        "Authorization": "Bearer " + token["access_token"],
        "X-Diapason-User-Id": "42",
        "X-Diapason-Customer-Id": "7",
        "X-Diapason-Mcp-Token": "private-api-token",
        "X-Diapason-Mcp-Scope": "3",
        "X-Diapason-Mcp-Base-Url": "https://company.example",
        "X-Diapason-Locale": "fr_FR",
    }
    with TestClient(app) as client:
        yield SimpleNamespace(
            runtime=runtime, app=app, client=client, headers=headers, token=token, scope="demo/7/42"
        )
