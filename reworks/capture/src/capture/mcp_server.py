"""Stateless MCP facade exposing the same Capture workflow as one model tool."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from capture.runtime import CaptureRuntime, public_result
from capture.security import CaptureSecurity, TokenValidationError


class CaptureJwtTokenVerifier(TokenVerifier):
    def __init__(self, security: CaptureSecurity) -> None:
        self._security = security

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        try:
            claims = self._security.jwt_auth.validate(token, roles=("chat", "admin"))
        except TokenValidationError:
            return None
        return AccessToken(
            token=token,
            active=True,
            scopes=["capture"],
            client_id=str(claims.get("sub") or "diapason-agent"),
            _meta={"customer_id": claims.get("customer_id")},
        )


def _request_identity(ctx: Context, security: CaptureSecurity):
    request = ctx.request_context.request
    if request is None or not hasattr(request, "headers"):
        raise ToolError("HTTP request context is unavailable")
    headers = request.headers
    authorization = (headers.get("Authorization") or "").strip()
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise ToolError("Missing Authorization bearer token")
    try:
        claims = security.jwt_auth.validate(token.strip(), roles=("chat", "admin"))
        return security.identity_from_headers(headers, claims)
    except (TokenValidationError, ValueError) as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        detail = getattr(exc, "detail", "Capture request context is invalid")
        raise ToolError(str(detail)) from exc


def create_mcp_server(
    runtime: CaptureRuntime,
    security: CaptureSecurity,
    config: dict[str, Any],
) -> FastMCP:
    block = config.get("mcp") if isinstance(config.get("mcp"), dict) else {}
    resource_url = str(block.get("resource_url") or "http://localhost:8000").rstrip("/")
    resource_host = urlparse(resource_url).netloc
    raw_hosts = block.get("allowed_hosts")
    allowed_hosts = [str(item) for item in raw_hosts] if isinstance(raw_hosts, list) else []
    if not allowed_hosts:
        allowed_hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
        if resource_host:
            allowed_hosts.append(resource_host)
    raw_origins = block.get("allowed_origins")
    allowed_origins = [str(item) for item in raw_origins] if isinstance(raw_origins, list) else []

    mcp = FastMCP(
        "Diapason Capture",
        stateless_http=True,
        json_response=True,
        token_verifier=CaptureJwtTokenVerifier(security),
        auth=AuthSettings(
            issuer_url=resource_url,
            resource_server_url=resource_url,
            required_scopes=["capture"],
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
    )

    @mcp.tool(name="capture", meta={"audience": "user"})
    async def capture_tool(
        trade_type: str,
        pdf_base64: str,
        ctx: Context,
        pdf_filename: str = "contract.pdf",
    ) -> dict[str, Any]:
        """Capture one trade from one PDF.

        Call only when the user has supplied both an explicit Diapason trade_type and one PDF.
        Pass the PDF bytes as base64; do not infer or change trade_type. The returned trade_xml,
        view_entity, menu_name, and trade_type are the prefilled trade-screen payload.
        """
        del pdf_filename  # Accepted for trace/UI attribution without affecting extraction logic.
        try:
            identity = _request_identity(ctx, security)
            pdf_bytes = runtime.decode_pdf_base64(pdf_base64)
            result = await runtime.execute(
                pdf_bytes=pdf_bytes,
                trade_type=trade_type,
                identity=identity,
                debug=False,
            )
            return public_result(result)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        except RuntimeError as exc:
            raise ToolError(str(exc)) from exc

    return mcp
