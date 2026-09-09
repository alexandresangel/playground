"""Exercise this application’s local adapter and telemetry primitives."""

import json

import httpx
import pytest
from openai import AsyncAzureOpenAI, AsyncOpenAI
from opentelemetry import trace

from pascal.adapters.azure_openai import AzureOpenAISettings, create_async_client
from pascal.adapters.diapason import parse_resolve_references_result
from pascal.observability import telemetry
from pascal.observability.telemetry import _headers, signal_endpoint


@pytest.mark.parametrize("mode", ["v1", "azure_dated"])
async def test_real_sdk_client_route_auth_and_ownership(mode, monkeypatch):
    requests = []

    async def responder(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "approved-deployment",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "OK"},
                    }
                ],
            },
        )

    monkeypatch.setenv("OPENAI_BASE_URL", "https://wrong.example/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "wrong-account-key")
    config = AzureOpenAISettings.from_mapping(
        {
            "endpoint": "https://azure.example",
            "deployment": "approved-deployment",
            "api_key": "fixture-only-key",
            "api_mode": mode,
            "api_version": "2024-10-21",
        }
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    client = create_async_client(config, http_client=http, timeout_seconds=3, max_retries=0)
    assert type(client) is (AsyncOpenAI if mode == "v1" else AsyncAzureOpenAI)
    await client.chat.completions.create(
        model=config.deployment, messages=[{"role": "user", "content": "Hello"}]
    )
    request = requests[0]
    assert request.url.host == "azure.example"
    assert json.loads(request.content)["model"] == config.deployment
    if mode == "v1":
        assert request.url.path == "/openai/v1/chat/completions"
        assert "api-version" not in request.url.params
        assert request.headers["Authorization"] == "Bearer fixture-only-key"
    else:
        assert request.url.path == "/openai/deployments/approved-deployment/chat/completions"
        assert request.url.params["api-version"] == "2024-10-21"
        assert request.headers["api-key"] == "fixture-only-key"
    assert "fixture-only-key" not in repr(config)
    await client.close()
    assert http.is_closed


def test_v1_endpoint_is_normalized_once_and_is_default():
    settings = AzureOpenAISettings.from_mapping(
        {
            "endpoint": "https://azure.example/openai/v1/",
            "deployment": "model",
            "api_key": "key",
            "api_version": "2024-10-21",
        }
    )
    assert settings.api_mode == "v1"
    assert settings.v1_base_url == "https://azure.example/openai/v1/"


@pytest.mark.parametrize(
    "override",
    [
        {"api_mode": "unknown"},
        {"api_mode": "azure_dated"},
        {"endpoint": "http://azure.example"},
        {"endpoint": "https://user:password@azure.example"},
        {"endpoint": "https://azure.example?key=value"},
        {"api_key": ""},
    ],
)
def test_client_configuration_rejects_ambiguous_or_unsafe_inputs(override):
    with pytest.raises(ValueError):
        AzureOpenAISettings.from_mapping(
            {
                "endpoint": "https://azure.example",
                "deployment": "model",
                "api_key": "key",
                **override,
            }
        )


def test_metrics_need_explicit_receiver_and_endpoint_modes_are_distinct(monkeypatch):
    for signal in ("TRACES", "LOGS", "METRICS"):
        monkeypatch.delenv(f"OTEL_EXPORTER_OTLP_{signal}_ENDPOINT", raising=False)
    monkeypatch.delenv("DIAPASON_OTLP_ENDPOINT_MODE", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.example")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    assert signal_endpoint("traces") == "https://collector.example"
    assert signal_endpoint("metrics") == ""
    monkeypatch.setenv("DIAPASON_OTLP_ENDPOINT_MODE", "standard")
    assert signal_endpoint("traces") == "https://collector.example/v1/traces"
    assert signal_endpoint("logs") == "https://collector.example/v1/logs"
    assert signal_endpoint("metrics") == ""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "https://metrics.example/v1/metrics")
    assert signal_endpoint("metrics") == "https://metrics.example/v1/metrics"


def test_metrics_headers_do_not_default_to_loki_tenant(monkeypatch):
    for name in (
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_METRICS_HEADERS",
        "OTEL_EXPORTER_OTLP_SCOPE_ORG_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TOKEN", "fixture")
    assert _headers("metrics") == {"Authorization": "Bearer fixture"}
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_METRICS_HEADERS", "Authorization=Bearer%20metrics,X-Scope-OrgID=team"
    )
    assert _headers("metrics") == {"Authorization": "Bearer metrics", "X-Scope-OrgID": "team"}


def test_business_failure_metric_when_trace_is_not_recording(monkeypatch):
    points = []

    class Counter:
        def add(self, value, labels):
            points.append((value, labels))

    monkeypatch.setattr(telemetry, "_operations", Counter())
    monkeypatch.setattr(telemetry, "_tracer", trace.NoOpTracerProvider().get_tracer("test"))
    with telemetry.operation("capture.run") as span:
        span.set_status(trace.Status(trace.StatusCode.ERROR))
    assert points == [(1, {"operation": "capture.run", "status": "error"})]


def test_resolver_failed_multiline_message_preserves_original_warning_contract():
    result = parse_resolve_references_result(
        "<basicResponse><success>false</success><message>first\nsecond</message>"
        "<extraInfo/></basicResponse>"
    )
    assert result["warnings"] == ["first\nsecond", "first", "second"]
