"""Unit tests for registry_client m2m URL resolution."""

from __future__ import annotations

import httpx
import pytest

from auth_m2m import normalize_issuer
from registry_client import (
    RegistryError,
    m2m_token_url_from_registry,
    registry_url_from_config,
    service_url,
)


def test_registry_url_from_config_required():
    assert (
        registry_url_from_config({"registry_url": " https://stor.example/services.json "})
        == "https://stor.example/services.json"
    )
    with pytest.raises(RegistryError, match="registry_url"):
        registry_url_from_config({})
    with pytest.raises(RegistryError, match="registry_url"):
        registry_url_from_config({"registry_url": "  "})


def test_service_url_m2m():
    services = {
        "m2m": {"name": "m2m", "group": "platform", "url": "https://m2m.example/token"},
    }
    assert service_url(services, "m2m") == "https://m2m.example/token"
    with pytest.raises(RegistryError):
        service_url(services, "missing")


def test_m2m_token_url_from_registry():
    body = {
        "services": {
            "m2m": {"url": "https://m2m.example/token"},
            "agent": {"url": "https://ai-agent.example"},
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    token_url = m2m_token_url_from_registry(
        "https://stor.example/registry/services.json?sig=x",
        client=client,
    )
    assert token_url == "https://m2m.example/token"
    assert normalize_issuer(token_url) == "https://m2m.example"


def test_registry_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    with pytest.raises(RegistryError, match="503"):
        m2m_token_url_from_registry("https://stor.example/registry/services.json", client=client)