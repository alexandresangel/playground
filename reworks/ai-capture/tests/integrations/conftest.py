"""Intercept only MCP's HTTP transport; keep JSON-RPC and parsing real."""

from unittest.mock import Mock

import httpx
import pytest

import mcp_rpc


@pytest.fixture
def mcp_transport(monkeypatch):
    real_client = httpx.Client

    def install(handler):
        factory = Mock(
            side_effect=lambda **kwargs: real_client(
                transport=httpx.MockTransport(handler), **kwargs
            )
        )
        monkeypatch.setattr(mcp_rpc.httpx, "Client", factory)
        return factory

    return install
