"""Compatibility security for the classic HTTP route and Capture MCP tool."""

from __future__ import annotations

import base64
import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jwt
from cryptography.hazmat.primitives.serialization import pkcs12
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from capture.config import capture_config
from capture.constants import (
    CUSTOMER_ID_HEADER,
    DIAPASON_API_TOKEN_HEADER,
    DIAPASON_BASE_URL_HEADER,
    DIAPASON_SCOPE_HEADER,
    JWT_ISSUER,
    JWT_KEYSTORE_ENV,
    JWT_KEYSTORE_PATH,
    JWT_REVOCATION_PATH,
    USER_ID_HEADER,
)


class TokenValidationError(Exception):
    """The caller JWT is invalid, revoked, or lacks an accepted role."""


class JwtAuth:
    """RS256/PKCS#12 validation compatible with diapason-agent's dia_jwt package."""

    def __init__(
        self,
        *,
        keystore_bytes: bytes,
        keystore_password: str,
        issuer: str = JWT_ISSUER,
        revocation_path: Path,
    ) -> None:
        self.issuer = issuer
        self._p12_data = keystore_bytes
        self._password = keystore_password
        self._revocation_path = revocation_path
        self._lock = threading.Lock()

    def _public_key(self) -> object:
        _key, certificate, _chain = pkcs12.load_key_and_certificates(
            self._p12_data, self._password.encode()
        )
        if certificate is None:
            raise ValueError("Keystore must contain a certificate")
        return certificate.public_key()

    def _revoked(self) -> dict[str, dict[str, Any]]:
        try:
            raw = json.loads(self._revocation_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {"jtis": {}, "subs": {}}
        if not isinstance(raw, dict):
            return {"jtis": {}, "subs": {}}
        jtis = raw.get("jtis") if isinstance(raw.get("jtis"), dict) else {}
        subs = raw.get("subs") if isinstance(raw.get("subs"), dict) else {}
        return {"jtis": jtis, "subs": subs}

    def validate(self, token: str, *, roles: Sequence[str]) -> dict[str, Any]:
        try:
            claims = jwt.decode(
                token,
                self._public_key(),
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"require": ["exp", "iat"]},
            )
        except Exception as exc:
            raise TokenValidationError(f"Invalid token: {exc}") from exc
        with self._lock:
            revoked = self._revoked()
        if claims.get("jti") in revoked["jtis"] or claims.get("sub") in revoked["subs"]:
            raise TokenValidationError("Token has been revoked")
        token_roles = claims.get("roles") or []
        if not isinstance(token_roles, list):
            token_roles = [token_roles]
        if not set(roles) & {str(role) for role in token_roles}:
            raise TokenValidationError("Insufficient role")
        return claims


@dataclass(frozen=True)
class DiapasonRequestContext:
    base_url: str
    scope: int
    api_token: str = field(repr=False)
    api_token_type: str = "Bearer"


@dataclass(frozen=True)
class CaptureIdentity:
    claims: dict[str, Any]
    instance: str
    user_id: int
    customer_id: int
    diapason: DiapasonRequestContext

    @property
    def scope_path(self) -> str:
        return f"{self.instance}/{self.customer_id}/{self.user_id}"


def _safe_instance(claims: Mapping[str, Any]) -> str:
    subject = str(claims.get("sub") or "").strip()
    if subject.startswith("instance:"):
        subject = subject.split(":", 1)[1]
    value = "".join(char if char.isalnum() or char in "._-" else "_" for char in subject)
    return value or "unknown"


def _integer_header(headers: Mapping[str, str], name: str) -> int:
    raw = (headers.get(name) or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail=f"Missing {name}")
    try:
        return int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be an integer") from exc


class CaptureSecurity:
    def __init__(self, jwt_auth: JwtAuth, config: dict[str, Any]) -> None:
        self.jwt_auth = jwt_auth
        block = capture_config(config)
        self._allow_http = block.get("allow_http_diapason") is True
        raw_hosts = block.get("allowed_diapason_hosts")
        self._allowed_hosts = (
            {str(host).strip().lower() for host in raw_hosts if str(host).strip()}
            if isinstance(raw_hosts, list)
            else set()
        )

    def claims_from_credentials(self, credentials: HTTPAuthorizationCredentials) -> dict[str, Any]:
        try:
            return self.jwt_auth.validate(credentials.credentials, roles=("chat", "admin"))
        except TokenValidationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def identity_from_headers(
        self, headers: Mapping[str, str], claims: dict[str, Any]
    ) -> CaptureIdentity:
        user_id = _integer_header(headers, USER_ID_HEADER)
        customer_id = _integer_header(headers, CUSTOMER_ID_HEADER)
        claim_customer = claims.get("customer_id")
        if claim_customer is not None and int(claim_customer) != customer_id:
            raise HTTPException(status_code=403, detail="customer_id mismatch")

        api_token = (headers.get(DIAPASON_API_TOKEN_HEADER) or "").strip()
        if not api_token:
            raise HTTPException(status_code=400, detail=f"Missing {DIAPASON_API_TOKEN_HEADER}")
        scope = _integer_header(headers, DIAPASON_SCOPE_HEADER)
        base_url = (headers.get(DIAPASON_BASE_URL_HEADER) or "").strip().rstrip("/")
        if not base_url:
            raise HTTPException(status_code=400, detail=f"Missing {DIAPASON_BASE_URL_HEADER}")
        parsed = urlparse(base_url)
        allowed_schemes = {"https", "http"} if self._allow_http else {"https"}
        if parsed.scheme.lower() not in allowed_schemes or not parsed.hostname:
            expected = "http(s)" if self._allow_http else "https"
            raise HTTPException(
                status_code=400,
                detail=f"{DIAPASON_BASE_URL_HEADER} must be an absolute {expected} URL",
            )
        if self._allowed_hosts and parsed.hostname.lower() not in self._allowed_hosts:
            raise HTTPException(status_code=403, detail="Diapason base URL host is not allowed")

        return CaptureIdentity(
            claims=claims,
            instance=_safe_instance(claims),
            user_id=user_id,
            customer_id=customer_id,
            diapason=DiapasonRequestContext(
                base_url=base_url,
                scope=scope,
                api_token=api_token,
            ),
        )


def build_security(base_dir: Path, config: dict[str, Any]) -> CaptureSecurity:
    jwt_block = config.get("jwt") if isinstance(config.get("jwt"), dict) else {}
    password = str(jwt_block.get("keystore_password") or "").strip()
    if not password:
        raise RuntimeError("Missing jwt.keystore_password in configuration")

    import os

    encoded = (os.getenv(JWT_KEYSTORE_ENV) or "").strip()
    if encoded:
        try:
            keystore_bytes = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise RuntimeError(f"{JWT_KEYSTORE_ENV} is not valid base64") from exc
    else:
        keystore_path = base_dir / JWT_KEYSTORE_PATH
        if not keystore_path.is_file():
            raise RuntimeError(
                f"Set {JWT_KEYSTORE_ENV} or place {JWT_KEYSTORE_PATH} in the app root"
            )
        keystore_bytes = keystore_path.read_bytes()

    revocation_path = base_dir / JWT_REVOCATION_PATH
    if not revocation_path.is_file():
        seed = jwt_block.get("revoked")
        if not isinstance(seed, dict):
            seed = {"jtis": {}, "subs": {}}
        revocation_path.parent.mkdir(parents=True, exist_ok=True)
        revocation_path.write_text(json.dumps(seed, indent=2), encoding="utf-8")

    return CaptureSecurity(
        JwtAuth(
            keystore_bytes=keystore_bytes,
            keystore_password=password,
            issuer=JWT_ISSUER,
            revocation_path=revocation_path,
        ),
        config,
    )
