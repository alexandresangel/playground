import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from capture.app import create_app
from capture.security import CaptureSecurity, JwtAuth


class FakeCatalog:
    ready = True

    def metadata(self) -> dict[str, Any]:
        return {"enabled": True, "trade_types": ["iamLoan"], "prompt_version": "test"}


class FakeRuntime:
    enabled = True
    max_pdf_bytes = 1024
    catalog = FakeCatalog()

    def initialize(self) -> None:
        pass

    def decode_pdf_base64(self, value: str) -> bytes:
        return base64.b64decode(value, validate=True)

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["pdf_bytes"].startswith(b"%PDF-")
        assert kwargs["trade_type"] == "iamLoan"
        return {
            "success": True,
            "trade_xml": '<trade><tradeType shortname="iamLoan"/></trade>',
            "view_entity": "loanDeposit",
            "menu_name": "loanDeposit",
            "trade_type": "iamLoan",
            "extracted_field_count": 1,
            "message": "",
            "warnings": [],
            "tool_trace": [],
            "session_artifacts": {"secret": "not-public"},
            "timings_ms": {"extract": 1},
        }


def _security_and_token(
    tmp_path: Path,
    *,
    roles: list[str] | None = None,
    revoked: bool = False,
) -> tuple[CaptureSecurity, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "capture-test")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(private_key, hashes.SHA256())
    )
    password = "test-password"
    keystore = pkcs12.serialize_key_and_certificates(
        name=b"capture-test",
        key=private_key,
        cert=certificate,
        cas=None,
        encryption_algorithm=BestAvailableEncryption(password.encode()),
    )
    revocation = tmp_path / "revoked.json"
    revocation.write_text(
        '{"jtis": {"test-jti": {}} , "subs": {}}' if revoked else '{"jtis": {}, "subs": {}}',
        encoding="utf-8",
    )
    security = CaptureSecurity(
        JwtAuth(
            keystore_bytes=keystore,
            keystore_password=password,
            revocation_path=revocation,
        ),
        {"capture": {"allow_http_diapason": True}},
    )
    token = jwt.encode(
        {
            "iss": "diapason-agent",
            "sub": "instance:test",
            "roles": roles or ["chat"],
            "customer_id": 7,
            "jti": "test-jti",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        private_key,
        algorithm="RS256",
    )
    return security, token


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Diapason-User-Id": "11",
        "X-Diapason-Customer-Id": "7",
        "X-Diapason-Mcp-Token": "downstream-secret",
        "X-Diapason-Mcp-Scope": "22",
        "X-Diapason-Mcp-Base-Url": "http://diapason.test",
    }


def _app(
    tmp_path: Path,
    *,
    roles: list[str] | None = None,
    revoked: bool = False,
) -> tuple[TestClient, str]:
    security, token = _security_and_token(tmp_path, roles=roles, revoked=revoked)
    app = create_app(
        config={
            "capture": {"allow_http_diapason": True},
            "mcp": {
                "resource_url": "http://testserver",
                "allowed_hosts": ["testserver"],
            },
        },
        runtime=FakeRuntime(),
        security=security,
        project_root=tmp_path,
    )
    return TestClient(app), token


def test_classic_metadata_and_capture_contract(tmp_path: Path) -> None:
    client, token = _app(tmp_path)
    with client:
        metadata = client.get(
            "/api/skills/intelligence-contract",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert metadata.status_code == 200, metadata.text
        assert metadata.json()["trade_types"] == ["iamLoan"]

        response = client.post(
            "/api/skills/intelligence-contract",
            headers=_headers(token),
            files={"pdf": ("contract.pdf", b"%PDF-test", "application/pdf")},
            data={"trade_type": "iamLoan", "session_id": "session-123"},
        )
    assert response.status_code == 200
    assert response.headers["X-Diapason-Chat-Session"] == "session-123"
    assert response.json()["trade_type"] == "iamLoan"
    assert "session_artifacts" not in response.json()


def test_customer_header_must_match_jwt(tmp_path: Path) -> None:
    client, token = _app(tmp_path)
    headers = _headers(token)
    headers["X-Diapason-Customer-Id"] = "8"
    with client:
        response = client.post(
            "/api/skills/intelligence-contract",
            headers=headers,
            files={"pdf": ("contract.pdf", b"%PDF-test", "application/pdf")},
            data={"trade_type": "iamLoan"},
        )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "customer_id mismatch"


def test_role_and_revocation_checks_match_legacy(tmp_path: Path) -> None:
    client, token = _app(tmp_path, roles=["refresh"])
    with client:
        wrong_role = client.get(
            "/api/skills/intelligence-contract",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert wrong_role.status_code == 401
    assert wrong_role.json()["detail"] == "Insufficient role"

    revoked_client, revoked_token = _app(tmp_path / "revoked", revoked=True)
    with revoked_client:
        revoked_response = revoked_client.get(
            "/api/skills/intelligence-contract",
            headers={"Authorization": f"Bearer {revoked_token}"},
        )
    assert revoked_response.status_code == 401
    assert revoked_response.json()["detail"] == "Token has been revoked"


def test_mcp_lists_single_capture_tool(tmp_path: Path) -> None:
    client, token = _app(tmp_path)
    headers = {
        **_headers(token),
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-06-18",
    }
    with client:
        response = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        call = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "capture",
                    "arguments": {
                        "trade_type": "iamLoan",
                        "pdf_base64": base64.b64encode(b"%PDF-test").decode(),
                    },
                },
            },
        )
    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["capture"]
    assert set(tools[0]["inputSchema"]["required"]) == {"trade_type", "pdf_base64"}
    assert call.status_code == 200, call.text
    assert call.json()["result"]["structuredContent"]["trade_type"] == "iamLoan"
