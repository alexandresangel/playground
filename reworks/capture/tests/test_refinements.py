import asyncio
import builtins
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langsmith import tracing_context
from langsmith.run_helpers import get_tracing_context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from test_app import FakeRuntime, _headers, _security_and_token
from test_workflow import FakeLlm, FakeResolver

from capture.adapters.catalog import PromptCatalog
from capture.adapters.diapason import DiapasonRequestContext
from capture.compatibility import LEGACY_CAPTURE_PATH, public_result
from capture.main import create_app
from capture.observability import telemetry
from capture.workflow.graph import CaptureWorkflow
from capture.workflow.service import CaptureRuntime


def test_http_only_adapter_does_not_import_mcp(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name != "mcp" and not name.startswith(("mcp.", "capture.api.mcp"))
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    security, token = _security_and_token(tmp_path)
    app = create_app(config={"mcp": {"enabled": False}}, runtime=FakeRuntime(), security=security)
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        assert client.post("/mcp").status_code == 404
        response = client.post(
            LEGACY_CAPTURE_PATH,
            headers=_headers(token),
            files={"pdf": ("contract.pdf", b"%PDF-test")},
            data={"trade_type": "iamLoan"},
        )
    assert response.status_code == 200
    assert response.json()["success"]
    assert response.headers["cache-control"] == "no-store"


def test_http_failure_is_private_and_body_limit_keeps_headers(tmp_path):
    class Failing(FakeRuntime):
        async def execute(self, **kwargs):
            raise RuntimeError("PRIVATE MODEL BODY")

    security, token = _security_and_token(tmp_path)
    app = create_app(config={"mcp": {"enabled": False}}, runtime=Failing(), security=security)
    with TestClient(app) as client:
        response = client.post(
            LEGACY_CAPTURE_PATH,
            headers=_headers(token),
            files={"pdf": ("contract.pdf", b"%PDF-test")},
            data={"trade_type": "iamLoan"},
        )
        assert response.status_code == 502
        assert "PRIVATE" not in response.text
        large = client.post(
            LEGACY_CAPTURE_PATH,
            headers={**_headers(token), "Content-Length": "100000", "X-Request-Id": "known-id"},
            content=b"x",
        )
        assert large.status_code == 413
        assert large.headers["x-request-id"] == "known-id"
        assert large.headers["x-content-type-options"] == "nosniff"
        assert large.headers["cache-control"] == "no-store"


async def test_disabled_runtime_and_owned_model_lifecycle(tmp_path, monkeypatch):
    class Model:
        closed = False

        def __init__(self, config):
            pass

        async def close(self):
            self.closed = True

    monkeypatch.setattr("capture.workflow.service.CaptureModel", Model)
    disabled = CaptureRuntime({"capture": {"enabled": False}}, tmp_path)
    assert disabled.llm is None and disabled.workflow is None
    disabled.initialize()
    await disabled.close()
    with pytest.raises(ValueError, match="disabled"):
        await disabled.execute(pdf_bytes=b"", trade_type="x", identity=None)
    owned = CaptureRuntime({}, tmp_path)
    await owned.close()
    assert owned.llm.closed
    borrowed = Model({})
    await CaptureRuntime({}, tmp_path, llm=borrowed).close()
    assert not borrowed.closed


async def test_total_runtime_deadline_cancels_work(tmp_path):
    cancelled = asyncio.Event()

    class Workflow:
        async def run(self, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    runtime = CaptureRuntime({"capture": {"turn_timeout_seconds": 0.01}}, tmp_path, llm=FakeLlm())
    runtime.workflow = Workflow()
    identity = SimpleNamespace(
        diapason=DiapasonRequestContext("https://diapason.example", 1, "private")
    )
    with pytest.raises(RuntimeError, match="timed out"):
        await runtime.execute(pdf_bytes=b"%PDF-test", trade_type="iamLoan", identity=identity)
    assert cancelled.is_set()


@pytest.mark.parametrize("failure", [False, True])
async def test_workflow_tracing_is_private_and_disabled_for_langsmith(failure, monkeypatch, caplog):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("test"))
    catalog = PromptCatalog(
        {"capture": {"catalog_backend": "filesystem"}}, Path(__file__).parents[1]
    )
    catalog.initialize()
    monkeypatch.setattr("capture.workflow.nodes.pdf_to_text", lambda _: "extracted contract text")

    class Model(FakeLlm):
        async def extract(self, **kwargs):
            assert get_tracing_context()["enabled"] is False
            if failure:
                raise RuntimeError("PRIVATE MODEL BODY")
            return await super().extract(**kwargs)

    try:
        with tracing_context(enabled=True):
            try:
                result = await CaptureWorkflow(catalog, Model()).run(
                    pdf_bytes=b"%PDF-private",
                    trade_type="iamLoan",
                    diapason=FakeResolver(),
                    max_pdf_bytes=1024,
                    temperature=0.5,
                )
            except RuntimeError:
                assert failure
            else:
                assert not failure
                assert "debug" not in result and "session_artifacts" not in result
                assert "steps" in result and "tool_trace" not in result
                public = public_result(result)
                assert "steps" not in public
                assert public["tool_trace"][1]["transport"] == "direct_http"
        spans = exporter.get_finished_spans()
        assert any(span.name == "capture.run" for span in spans)
        serialized = json.dumps([span.to_json() for span in spans])
        assert "PRIVATE MODEL BODY" not in serialized + caplog.text
        assert "extracted contract text" not in serialized
        assert not any(span.events for span in spans)
        assert (
            next(span for span in spans if span.name == "capture.run").status.is_ok is not failure
        )
    finally:
        provider.shutdown()
