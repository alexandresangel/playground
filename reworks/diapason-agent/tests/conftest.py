import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from pascal.agent.prompt import PromptProvider
from pascal.agent.service import ChatService
from pascal.agent.state import ModelReply
from pascal.config import AgentLimits
from pascal.security.deps import Identity
from pascal.security.jwt import JwtAuth
from pascal.sessions.blob_store import _add_turns, _llm_turns, _new_record, _summary
from pascal.tools.context import McpCluster, McpServerContext
from pascal.tools.registry import ToolRegistry


class MemoryStore:
    """Test double only. Production never silently falls back to volatile history."""

    backend = "test-memory"

    def __init__(self):
        self.records = {}
        self.writes = 0
        self.fail_write = False

    def create_session(self, scope, title=""):
        record = _new_record(scope, title)
        self.records[(scope, record["session_id"])] = record
        return deepcopy(record)

    def get_session(self, session_id, scope=None):
        return deepcopy(self.records.get((scope, session_id)))

    def resolve_session_id(self, scope, session_id):
        if session_id:
            if (scope, session_id) not in self.records:
                raise KeyError(session_id)
            return session_id
        return self.create_session(scope)["session_id"]

    def get_turns(self, session_id, scope):
        return _llm_turns(self.records[(scope, session_id)]["turns"], 30)

    def append_turn(self, session_id, scope, user, assistant, **kwargs):
        if self.fail_write:
            raise RuntimeError("blob secret URL must never leave this boundary")
        self.writes += 1
        _add_turns(self.records[(scope, session_id)], user, assistant, 30, **kwargs)

    def list_sessions(self, scope):
        return [
            _summary(record)
            for (record_scope, _), record in self.records.items()
            if record_scope == scope
        ]

    def delete_session(self, session_id, scope):
        return self.records.pop((scope, session_id), None) is not None


class FakeModel:
    def __init__(self, replies=None):
        self.replies = list(replies or [ModelReply(content="Hello")])
        self.requests = []
        self.started = asyncio.Event()
        self.block = False

    async def complete(self, messages, tools, max_tokens, on_delta):
        self.requests.append((deepcopy(messages), deepcopy(tools), max_tokens))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if reply.content:
            await on_delta(reply.content)
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        return reply


class FakeMcp:
    def __init__(self, rows=None, result=None):
        self.rows = (
            rows
            if rows is not None
            else [
                {
                    "name": "balance",
                    "description": "Get actual balance",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"account": {"type": "string"}},
                        "required": ["account"],
                        "additionalProperties": False,
                    },
                    "annotations": {"readOnlyHint": True},
                }
            ]
        )
        self.result = result or {"content": [{"type": "text", "text": "100 EUR"}]}
        self.requests = []
        self.fail = False

    async def request(self, server, method, params):
        self.requests.append((server, method, params))
        if method == "tools/list":
            return {"tools": deepcopy(self.rows)}
        if self.fail:
            raise RuntimeError("SECRET_REMOTE_BODY")
        return deepcopy(self.result)


@pytest.fixture
def config():
    return {
        "mcp": {
            "default": {
                "server_url": "https://mcp.example/mcp",
                "config_key": Fernet.generate_key().decode(),
            }
        },
        "ui": {"assistant_name": "Pascal"},
        "azure_openai": {},
        "agent": {},
    }


@pytest.fixture
def identity():
    return Identity(
        {"sub": "instance:demo", "roles": ["chat"], "customer_id": 12},
        "demo",
        7,
        12,
        McpCluster((McpServerContext("default", "Diapason", "https://mcp.example/mcp"),)),
    )


@pytest.fixture
def service_factory(config):
    def make(model=None, transport=None, limits=None, store=None):
        limits = limits or AgentLimits()
        model, transport, store = (
            model or FakeModel(),
            transport or FakeMcp(),
            store or MemoryStore(),
        )
        return ChatService(
            model=model,
            transport=transport,
            store=store,
            registry=ToolRegistry(transport, limits, []),
            prompts=PromptProvider(config, Path.cwd(), "You are Pascal."),
            config=config,
            limits=limits,
        )

    return make


@pytest.fixture
def auth(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Pascal test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=2))
        .sign(key, hashes.SHA256())
    )
    blob = pkcs12.serialize_key_and_certificates(
        b"pascal", key, cert, None, serialization.BestAvailableEncryption(b"test")
    )
    return JwtAuth(
        keystore_bytes=blob,
        keystore_password="test",
        issuer="diapason-agent",
        revocation_path=tmp_path / "revoked.json",
    )


@pytest.fixture
def headers(auth):
    minted = auth.mint(sub="instance:demo", roles=["chat"], customer_id=12, ttl_seconds=3600)
    return {
        "Authorization": "Bearer " + minted["access_token"],
        "X-Diapason-User-Id": "7",
        "X-Diapason-Customer-Id": "12",
        "X-Diapason-Mcp-Token": "API-TOKEN",
        "X-Diapason-Mcp-Scope": "5",
        "X-Diapason-Mcp-Base-Url": "https://diapason.example",
    }
