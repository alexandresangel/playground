"""Capture's Diapason server and encrypted caller credentials."""

import json
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from starlette.datastructures import Headers

from mcp_context import mcp_cluster_from_request


@pytest.fixture
def mcp_config():
    return {
        "mcp": {
            "default": {
                "server_url": " https://mcp.example/mcp/ ",
                "config_key": Fernet.generate_key().decode(),
                "label": "Company Diapason",
                "headers": {"X-Custom": "1", "Authorization": "must-be-replaced"},
            }
        }
    }


@pytest.fixture
def caller():
    return {
        "X-Diapason-Mcp-Token": "caller-token",
        "X-Diapason-Mcp-Scope": "3",
        "X-Diapason-Mcp-Base-Url": "https://company.example/diapason/",
    }


def test_request_credentials_are_encrypted_for_the_default_diapason_server(mcp_config, caller):
    cluster = mcp_cluster_from_request(SimpleNamespace(headers=Headers(caller)), mcp_config)
    server = cluster.diapason
    assert cluster.servers == (server,)
    assert server.server_id == "default"
    assert server.server_url == "https://mcp.example/mcp"
    assert server.label == "Company Diapason"
    assert server.request_headers["X-Custom"] == "1"
    bearer = server.request_headers["Authorization"].removeprefix("Bearer ")
    decoded = json.loads(
        Fernet(mcp_config["mcp"]["default"]["config_key"]).decrypt(bearer.encode())
    )
    assert decoded == {
        "api_token": "caller-token",
        "scope": 3,
        "base_url": "https://company.example/diapason",
    }


@pytest.mark.parametrize(
    "configured,header,expected",
    [
        ("configured", "requested", "configured"),
        (None, "requested", "requested"),
        (None, None, "2024-11-05"),
    ],
)
def test_protocol_version_precedence(mcp_config, caller, configured, header, expected):
    if configured:
        mcp_config["mcp"]["default"]["protocol_version"] = configured
    if header:
        caller["X-Diapason-Mcp-Protocol-Version"] = header
    cluster = mcp_cluster_from_request(SimpleNamespace(headers=Headers(caller)), mcp_config)
    assert cluster.diapason.protocol_version == expected


@pytest.mark.parametrize(
    "key,value,message",
    [
        ("server_url", "", "Missing mcp.default.server_url"),
        ("config_key", "", "Missing mcp.default.config_key"),
        ("config_key", "not-a-fernet-key", "Invalid mcp.default.config_key"),
    ],
)
def test_invalid_server_configuration_is_a_service_error(mcp_config, caller, key, value, message):
    mcp_config["mcp"]["default"][key] = value
    with pytest.raises(HTTPException) as error:
        mcp_cluster_from_request(SimpleNamespace(headers=Headers(caller)), mcp_config)
    assert error.value.status_code == 500
    assert message in error.value.detail
