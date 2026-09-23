import pytest

import telemetry


@pytest.fixture(autouse=True)
def clean_otel_env(monkeypatch):
    import os
    for name in os.environ:
        if name.startswith("OTEL_"):
            monkeypatch.delenv(name)


def test_platform_endpoint_and_credentials(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector/otlp/")
    monkeypatch.setenv("OTEL_BEARER_TOKEN", "platform-token")
    monkeypatch.setenv("OTEL_ORG_ID", "capture-team")
    assert telemetry._otlp_signal_url("traces") == "https://collector/otlp/v1/traces"
    assert telemetry._otlp_signal_url("logs") == "https://collector/otlp/v1/logs"
    assert telemetry._headers_for(logs=False) == {"Authorization": "Bearer platform-token"}
    assert telemetry._headers_for(logs=True) == {"Authorization": "Bearer platform-token", "X-Scope-OrgID": "capture-team"}


def test_jaeger_trace_only_setup_stays_trace_only(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4318/v1/traces")
    assert telemetry._otel_enabled_for_traces()
    assert not telemetry._otel_enabled_for_logs()
    assert telemetry._otlp_signal_url("traces") == "http://localhost:4318/v1/traces"


def test_signal_endpoint_and_header_precedence(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://traces/custom")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer%20common")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", "Authorization=Bearer%20trace")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_HEADERS", "Authorization=Bearer%20logs")
    monkeypatch.setenv("OTEL_BEARER_TOKEN", "unused")
    assert telemetry._otlp_signal_url("traces") == "http://traces/custom"
    assert telemetry._headers_for(logs=False) == {"Authorization": "Bearer trace"}
    assert telemetry._headers_for(logs=True) == {"Authorization": "Bearer logs"}


def test_legacy_settings_still_work(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector/v1/traces")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TOKEN", "legacy-token")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_SCOPE_ORG_ID", "legacy-team")
    assert telemetry._otlp_signal_url("logs") == "http://collector/v1/logs"
    assert telemetry._headers_for(logs=True)["X-Scope-OrgID"] == "legacy-team"
    assert telemetry._headers_for(logs=False)["Authorization"] == "Bearer legacy-token"


def test_capture_default_service_name():
    assert telemetry._resource_from_env().attributes["service.name"] == "ai-capture"
