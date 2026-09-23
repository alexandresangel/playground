"""Validate platform m2m Bearer JWTs via JWKS (RS256 + iss + exact scope)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from mcp_context import McpCluster, mcp_from_request

try:
    from fastapi import Depends, HTTPException, Request
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
except ImportError as exc:  # pragma: no cover
    raise ImportError("fastapi is required for auth_m2m") from exc

log = logging.getLogger(__name__)

DEFAULT_REQUIRED_SCOPE = "ai-capture"
DEFAULT_JWKS_CACHE_SECONDS = 600
DEFAULT_JWKS_MAX_STALE_SECONDS = 3600
DEFAULT_CLOCK_SKEW_SECONDS = 60
JWKS_HTTP_TIMEOUT_SECONDS = 5.0


class TokenValidationError(Exception):
    pass


def normalize_issuer(raw: str, *, allow_http: bool = False) -> str:
    """Canonical m2m issuer: scheme://host[:port], no path, no trailing slash.

    Accepts registry ``…/token`` and strips that path; other paths fail closed.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("issuer must be a non-empty URL")
    parsed = urlparse(text)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError("issuer must be an absolute http(s) URL with a host")
    if parsed.scheme == "http" and not allow_http:
        raise ValueError("issuer must use https")
    path = (parsed.path or "").rstrip("/")
    if path == "/token":
        path = ""
    elif path.endswith("/token"):
        raise ValueError("issuer must not include a path other than /token")
    elif path:
        raise ValueError("issuer must not include a path (except optional /token)")
    return f"{parsed.scheme}://{parsed.netloc}"


def scope_has(scope_claim: object, required: str) -> bool:
    """True if required is an exact ASCII-space-delimited member of scope_claim."""
    if not required:
        return False
    if not isinstance(scope_claim, str):
        return False
    members = [p for p in scope_claim.split(" ") if p]
    return required in members


def instance_from_client_id(client_id: object) -> str:
    text = str(client_id or "").strip()
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in text)
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
        return f"{self.instance}/{self.customer_id}/{self.user_id}"


@dataclass
class _JwksCache:
    keys_by_kid: Dict[str, Any]
    fetched_at: float
    jwks_url: str


class M2MAuth:
    def __init__(
        self,
        *,
        issuer: str,
        jwks_url: Optional[str] = None,
        required_scope: str = DEFAULT_REQUIRED_SCOPE,
        jwks_cache_seconds: int = DEFAULT_JWKS_CACHE_SECONDS,
        jwks_max_stale_seconds: int = DEFAULT_JWKS_MAX_STALE_SECONDS,
        clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
        allow_http: bool = False,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.issuer = normalize_issuer(issuer, allow_http=allow_http)
        self.allow_http = allow_http
        if jwks_url:
            jwks = jwks_url.strip()
            parsed = urlparse(jwks)
            if parsed.scheme not in ("https", "http") or not parsed.netloc:
                raise ValueError("jwks_url must be an absolute http(s) URL")
            if parsed.scheme == "http" and not allow_http:
                raise ValueError("jwks_url must use https")
            self.jwks_url = jwks.rstrip("/")
        else:
            self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
        self.required_scope = required_scope
        self.jwks_cache_seconds = max(1, int(jwks_cache_seconds))
        self.jwks_max_stale_seconds = max(self.jwks_cache_seconds, int(jwks_max_stale_seconds))
        self.clock_skew_seconds = max(0, int(clock_skew_seconds))
        self._client = http_client
        self._owns_client = http_client is None
        self._lock = threading.Lock()
        self._cache: Optional[_JwksCache] = None

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=JWKS_HTTP_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
        return self._client

    def _fetch_jwks(self) -> Dict[str, Any]:
        url = self.jwks_url
        resp = self._http().get(url)
        if resp.status_code != 200:
            raise TokenValidationError(f"JWKS fetch failed: HTTP {resp.status_code}")
        # Refuse cross-host redirects by not following; also check final URL host.
        if urlparse(str(resp.url)).netloc != urlparse(url).netloc:
            raise TokenValidationError("JWKS redirect to unexpected host")
        try:
            body = resp.json()
        except ValueError as exc:
            raise TokenValidationError("JWKS response is not JSON") from exc
        keys = body.get("keys") if isinstance(body, dict) else None
        if not isinstance(keys, list) or not keys:
            raise TokenValidationError("JWKS has no keys")
        by_kid: Dict[str, Any] = {}
        for jwk in keys:
            if not isinstance(jwk, dict):
                continue
            kid = jwk.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            try:
                by_kid[kid] = RSAAlgorithm.from_jwk(jwk)
            except Exception as exc:
                log.warning("skip JWKS key kid=%s: %s", kid, exc)
        if not by_kid:
            raise TokenValidationError("JWKS has no usable RS keys")
        return by_kid

    def _cache_age(self, now: float) -> Optional[float]:
        if self._cache is None:
            return None
        return now - self._cache.fetched_at

    def _refresh_cache(self, *, force: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            age = self._cache_age(now)
            if (
                not force
                and self._cache is not None
                and age is not None
                and age < self.jwks_cache_seconds
            ):
                return
        try:
            keys = self._fetch_jwks()
        except Exception as exc:
            with self._lock:
                if self._cache is None:
                    raise TokenValidationError("JWKS unavailable (cold cache)") from exc
                age = self._cache_age(time.monotonic())
                if age is None or age > self.jwks_max_stale_seconds:
                    raise TokenValidationError("JWKS stale beyond max age") from exc
                log.warning(
                    "JWKS refresh failed; using last-good cache age=%.0fs: %s",
                    age,
                    exc,
                )
            return
        with self._lock:
            self._cache = _JwksCache(
                keys_by_kid=keys,
                fetched_at=time.monotonic(),
                jwks_url=self.jwks_url,
            )

    def _signing_key(self, kid: str):
        self._refresh_cache(force=False)
        with self._lock:
            cache = self._cache
            if cache is None:
                raise TokenValidationError("JWKS unavailable (cold cache)")
            key = cache.keys_by_kid.get(kid)
        if key is not None:
            return key
        # Unknown kid — force refresh once (rotation).
        self._refresh_cache(force=True)
        with self._lock:
            cache = self._cache
            if cache is None:
                raise TokenValidationError("JWKS unavailable (cold cache)")
            key = cache.keys_by_kid.get(kid)
        if key is None:
            raise TokenValidationError("Unknown kid")
        return key

    def validate(self, token: str) -> Dict[str, Any]:
        if not token or not str(token).strip():
            raise TokenValidationError("Missing token")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError as exc:
            raise TokenValidationError("Invalid token header") from exc
        alg = header.get("alg")
        if alg != "RS256":
            raise TokenValidationError("Unsupported algorithm")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TokenValidationError("Missing kid")
        key = self._signing_key(kid)
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                leeway=self.clock_skew_seconds,
                options={
                    "require": ["exp", "iat", "iss"],
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
        except jwt.exceptions.ExpiredSignatureError as exc:
            raise TokenValidationError("Token expired") from exc
        except jwt.exceptions.PyJWTError as exc:
            raise TokenValidationError("Invalid token") from exc

        raw_iss = claims.get("iss")
        if not isinstance(raw_iss, str):
            raise TokenValidationError("Missing iss")
        try:
            claim_iss = normalize_issuer(raw_iss, allow_http=self.allow_http)
        except ValueError as exc:
            raise TokenValidationError("Invalid iss") from exc
        if claim_iss != self.issuer:
            raise TokenValidationError("Invalid issuer")

        if not scope_has(claims.get("scope"), self.required_scope):
            raise TokenValidationError("Insufficient scope")

        client_id = claims.get("client_id")
        if not isinstance(client_id, str) or not client_id.strip():
            raise TokenValidationError("Missing client_id")
        return claims

    def warmup(self) -> None:
        """Optional eager JWKS fetch at startup."""
        self._refresh_cache(force=True)


def m2m_from_config(config: Dict[str, Any]) -> M2MAuth:
    """Build M2MAuth; issuer always from config.registry_url → services.m2m.url."""
    from registry_client import (
        RegistryError,
        m2m_token_url_from_registry,
        registry_url_from_config,
    )

    block = config.get("m2m") if isinstance(config.get("m2m"), dict) else {}
    allow_http = bool(block.get("allow_http", False))
    jwks_url = str(block.get("jwks_url") or "").strip() or None
    required_scope = (
        str(block.get("required_scope") or DEFAULT_REQUIRED_SCOPE).strip() or DEFAULT_REQUIRED_SCOPE
    )

    try:
        registry_url = registry_url_from_config(config)
        token_url = m2m_token_url_from_registry(registry_url)
        issuer = normalize_issuer(token_url, allow_http=allow_http)
    except (RegistryError, ValueError) as exc:
        raise RuntimeError(f"Failed to resolve m2m issuer from config.registry_url: {exc}") from exc
    log.info("m2m issuer from registry: %s", issuer)

    return M2MAuth(
        issuer=issuer,
        jwks_url=jwks_url,
        required_scope=required_scope,
        jwks_cache_seconds=int(block.get("jwks_cache_seconds") or DEFAULT_JWKS_CACHE_SECONDS),
        jwks_max_stale_seconds=int(
            block.get("jwks_max_stale_seconds") or DEFAULT_JWKS_MAX_STALE_SECONDS
        ),
        clock_skew_seconds=int(block.get("clock_skew_seconds", DEFAULT_CLOCK_SKEW_SECONDS)),
        allow_http=allow_http,
    )


def m2m_deps(
    auth: M2MAuth,
    *,
    user_header: str = "X-Diapason-User-Id",
    customer_header: str = "X-Diapason-Customer-Id",
) -> dict:
    bearer = HTTPBearer(auto_error=True)

    def _claims(credentials: HTTPAuthorizationCredentials) -> dict:
        try:
            return auth.validate(credentials.credentials)
        except TokenValidationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def require_capture(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
        return _claims(credentials)

    def require_refresh(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
        return _claims(credentials)

    def _parse_int_header(raw: str) -> int:
        text = (raw or "").strip()
        if not text:
            raise ValueError("missing")
        return int(text)

    def get_identity(request: Request, claims: dict = Depends(require_capture)) -> Identity:
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
        return Identity(
            claims=claims,
            instance=instance_from_client_id(claims.get("client_id")),
            user_id=user_id,
            customer_id=customer_id,
            mcp=mcp_from_request(request),
        )

    return {
        "require_capture": require_capture,
        "require_refresh": require_refresh,
        "get_identity": get_identity,
    }


def configure_auth(
    config: Dict[str, Any],
    *,
    warmup: bool = True,
) -> Tuple[M2MAuth, Callable, Callable, Callable]:
    auth = m2m_from_config(config)
    if warmup:
        try:
            auth.warmup()
        except TokenValidationError as exc:
            log.warning("m2m JWKS warmup failed (will retry on request): %s", exc)
    deps = m2m_deps(auth)
    return auth, deps["get_identity"], deps["require_refresh"], deps["require_capture"]