"""FastAPI helpers (requires fastapi in the host app)."""

from __future__ import annotations

from dataclasses import dataclass

from dia_jwt.auth import JwtAuth, TokenValidationError
from mcp_context import McpCluster, mcp_from_request

try:
    from fastapi import Depends, HTTPException, Request
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
except ImportError as exc:  # pragma: no cover
    raise ImportError("fastapi is required for dia_jwt.fastapi") from exc


def _instance_from_claims(claims: dict) -> str:
    sub = str(claims.get("sub") or "").strip()
    if sub.startswith("instance:"):
        sub = sub.split(":", 1)[1]
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in sub)
    return safe or "unknown"


@dataclass(frozen=True)
class Identity:
    claims: dict
    instance: str
    user_id: int
    customer_id: int
    mcp: McpCluster

    @property
    def scope_path(self) -> str:
        """Storage path prefix: instance/customer/user"""
        return f"{self.instance}/{self.customer_id}/{self.user_id}"


def jwt_deps(
    auth: JwtAuth,
    *,
    user_header: str = "X-Diapason-User-Id",
    customer_header: str = "X-Diapason-Customer-Id",
    enforce_customer: bool = True,
) -> dict:
    bearer = HTTPBearer(auto_error=True)

    def _claims(credentials: HTTPAuthorizationCredentials, roles: tuple[str, ...]) -> dict:
        try:
            return auth.validate(credentials.credentials, roles=roles)
        except TokenValidationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def require_admin(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
        return _claims(credentials, ("admin",))

    def require_chat(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
        return _claims(credentials, ("chat", "admin"))

    def require_refresh(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
        return _claims(credentials, ("refresh",))

    def _parse_int_header(raw: str) -> int:
        text = (raw or "").strip()
        if not text:
            raise ValueError("missing")
        return int(text)

    def get_identity(request: Request, claims: dict = Depends(require_chat)) -> Identity:
        user_raw = request.headers.get(user_header, "")
        customer_raw = request.headers.get(customer_header, "")
        try:
            user_id = _parse_int_header(user_raw)
            customer_id = _parse_int_header(customer_raw)
        except ValueError as exc:
            if str(exc) == "missing":
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing {user_header} or {customer_header}",
                ) from exc
            raise HTTPException(status_code=400, detail="user_id and customer_id must be integers") from exc
        claim_customer = claims.get("customer_id")
        if enforce_customer and claim_customer is not None and int(claim_customer) != customer_id:
            raise HTTPException(status_code=403, detail="customer_id mismatch")
        return Identity(
            claims=claims,
            instance=_instance_from_claims(claims),
            user_id=user_id,
            customer_id=customer_id,
            mcp=mcp_from_request(request),
        )

    return {
        "require_admin": require_admin,
        "require_chat": require_chat,
        "require_refresh": require_refresh,
        "get_identity": get_identity,
    }