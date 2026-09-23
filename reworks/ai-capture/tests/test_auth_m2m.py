"""Unit tests for m2m JWKS auth (issuer normalize, exact scope, max-stale)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from auth_m2m import (
    M2MAuth,
    TokenValidationError,
    normalize_issuer,
    scope_has,
)


ISSUER = "https://m2m.example"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
KID = "test-key"


@pytest.fixture(scope="module")
def rsa_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture(scope="module")
def jwk_dict(rsa_pair) -> Dict[str, Any]:
    _, public_key = rsa_pair
    raw = json.loads(RSAAlgorithm.to_jwk(public_key))
    raw["kid"] = KID
    raw["use"] = "sig"
    raw["alg"] = "RS256"
    return raw


def _mint(
    private_key,
    *,
    issuer: str = ISSUER,
    scope: str = "ai-capture",
    client_id: str = "dia-app-68",
    exp_delta: timedelta = timedelta(minutes=15),
    alg: str = "RS256",
    kid: str = KID,
    extra: Dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "iss": issuer,
        "client_id": client_id,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int((now + exp_delta).timestamp()),
    }
    if extra:
        payload.update(extra)
        for key, value in extra.items():
            if value is None:
                payload.pop(key, None)
    headers = {"kid": kid, "alg": alg}
    return jwt.encode(payload, private_key, algorithm=alg, headers=headers)


def _transport(jwk_dict: Dict[str, Any], *, status: int = 200, body: Any = None):
    payload = body if body is not None else {"keys": [jwk_dict]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jwks.json") or "jwks" in request.url.path:
            if status != 200:
                return httpx.Response(status, text="fail")
            return httpx.Response(200, json=payload)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _auth(jwk_dict: Dict[str, Any], **kwargs) -> M2MAuth:
    client = httpx.Client(transport=_transport(jwk_dict), follow_redirects=False)
    return M2MAuth(
        issuer=ISSUER,
        jwks_url=JWKS_URL,
        http_client=client,
        jwks_cache_seconds=kwargs.pop("jwks_cache_seconds", 600),
        jwks_max_stale_seconds=kwargs.pop("jwks_max_stale_seconds", 3600),
        **kwargs,
    )


class TestNormalizeIssuer:
    def test_strip_token_path(self):
        assert normalize_issuer("https://m2m.example/token") == "https://m2m.example"

    def test_trailing_slash(self):
        assert normalize_issuer("https://m2m.example/") == "https://m2m.example"

    def test_reject_other_path(self):
        with pytest.raises(ValueError):
            normalize_issuer("https://m2m.example/foo")

    def test_reject_nested_token(self):
        with pytest.raises(ValueError):
            normalize_issuer("https://m2m.example/foo/token")

    def test_http_requires_allow(self):
        with pytest.raises(ValueError):
            normalize_issuer("http://localhost:8080")
        assert normalize_issuer("http://localhost:8080", allow_http=True) == "http://localhost:8080"


class TestScopeHas:
    def test_exact_member(self):
        assert scope_has("ai-capture ai-agent", "ai-capture")
        assert not scope_has("not-ai-capture", "ai-capture")
        assert not scope_has("ai-capture-admin", "ai-capture")
        assert not scope_has("ai-capturex", "ai-capture")
        assert not scope_has(["ai-capture"], "ai-capture")


class TestValidate:
    def test_happy_path(self, rsa_pair, jwk_dict):
        private_key, _ = rsa_pair
        auth = _auth(jwk_dict)
        token = _mint(private_key, scope="ai-capture ai-agent")
        claims = auth.validate(token)
        assert claims["client_id"] == "dia-app-68"
        assert claims["iss"] == ISSUER

    def test_iss_trailing_slash_on_claim(self, rsa_pair, jwk_dict):
        private_key, _ = rsa_pair
        auth = _auth(jwk_dict)
        token = _mint(private_key, issuer=ISSUER + "/")
        assert auth.validate(token)["client_id"] == "dia-app-68"

    def test_wrong_iss(self, rsa_pair, jwk_dict):
        private_key, _ = rsa_pair
        auth = _auth(jwk_dict)
        token = _mint(private_key, issuer="https://evil.example")
        with pytest.raises(TokenValidationError, match="issuer"):
            auth.validate(token)

    def test_missing_scope(self, rsa_pair, jwk_dict):
        private_key, _ = rsa_pair
        auth = _auth(jwk_dict)
        token = _mint(private_key, scope="ai-agent")
        with pytest.raises(TokenValidationError, match="scope"):
            auth.validate(token)

    def test_substring_scope_rejected(self, rsa_pair, jwk_dict):
        private_key, _ = rsa_pair
        auth = _auth(jwk_dict)
        for scope in ("not-ai-capture", "ai-capture-admin", "ai-capturex"):
            token = _mint(private_key, scope=scope)
            with pytest.raises(TokenValidationError, match="scope"):
                auth.validate(token)

    def test_wrong_alg(self, rsa_pair, jwk_dict):
        private_key, _ = rsa_pair
        auth = _auth(jwk_dict)
        # HS256 with a random secret — header alg must be rejected before verify.
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "iss": ISSUER,
                "client_id": "x",
                "scope": "ai-capture",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
            },
            "test-secret-with-at-least-32-bytes",
            algorithm="HS256",
            headers={"kid": KID},
        )
        with pytest.raises(TokenValidationError, match="algorithm"):
            auth.validate(token)

    def test_expired(self, rsa_pair, jwk_dict):
        private_key, _ = rsa_pair
        auth = _auth(jwk_dict)
        token = _mint(private_key, exp_delta=timedelta(minutes=-5))
        with pytest.raises(TokenValidationError, match="expired"):
            auth.validate(token)

    def test_jwks_max_stale_fail_closed(self, rsa_pair, jwk_dict):
        private_key, _ = rsa_pair
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json={"keys": [jwk_dict]})
            return httpx.Response(503, text="down")

        client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        auth = M2MAuth(
            issuer=ISSUER,
            jwks_url=JWKS_URL,
            http_client=client,
            jwks_cache_seconds=1,
            jwks_max_stale_seconds=2,
        )
        token = _mint(private_key)
        assert auth.validate(token)
        # Soft TTL expired; refresh fails but within max stale → OK
        auth._cache.fetched_at = time.monotonic() - 1.5  # type: ignore[union-attr]
        assert auth.validate(token)
        # Past max stale → fail closed
        auth._cache.fetched_at = time.monotonic() - 3.0  # type: ignore[union-attr]
        with pytest.raises(TokenValidationError, match="stale"):
            auth.validate(token)

    def test_cold_cache_fail_closed(self, jwk_dict):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="down")

        client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        auth = M2MAuth(issuer=ISSUER, jwks_url=JWKS_URL, http_client=client)
        with pytest.raises(TokenValidationError, match="cold"):
            auth.validate(
                jwt.encode(
                    {
                        "iss": ISSUER,
                        "client_id": "x",
                        "scope": "ai-capture",
                        "iat": int(time.time()),
                        "exp": int(time.time()) + 60,
                    },
                    rsa.generate_private_key(public_exponent=65537, key_size=2048),
                    algorithm="RS256",
                    headers={"kid": KID},
                )
            )


def test_unknown_kid_refreshes_once_for_key_rotation(rsa_pair, jwk_dict):
    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rotated_jwk = json.loads(RSAAlgorithm.to_jwk(rotated.public_key()))
    rotated_jwk["kid"] = "rotated"
    calls = []

    def handler(request):
        calls.append(request)
        keys = [jwk_dict] if len(calls) == 1 else [rotated_jwk]
        return httpx.Response(200, json={"keys": keys})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        auth = M2MAuth(issuer=ISSUER, http_client=client)
        assert auth.validate(_mint(rsa_pair[0]))
        assert auth.validate(_mint(rotated, kid="rotated"))
        assert len(calls) == 2
        with pytest.raises(TokenValidationError, match="Unknown kid"):
            auth.validate(_mint(rotated, kid="never-published"))
        assert len(calls) == 3


@pytest.mark.parametrize("override", [{"exp": None}, {"iat": None}, {"iss": None}, {"client_id": ""}])
def test_required_claims_are_rejected(rsa_pair, jwk_dict, override):
    with pytest.raises(TokenValidationError):
        _auth(jwk_dict).validate(_mint(rsa_pair[0], extra=override))


def test_registry_configures_capture_scope_and_zero_clock_skew(monkeypatch):
    import registry_client
    from auth_m2m import m2m_from_config

    resolved = []
    def resolve(url):
        resolved.append(url)
        return ISSUER + "/token"
    monkeypatch.setattr(registry_client, "m2m_token_url_from_registry", resolve)
    config = {"registry_url": "https://registry.example/services.json", "m2m": {"clock_skew_seconds": 0}}
    auth = m2m_from_config(config)
    assert auth.issuer == ISSUER
    assert auth.jwks_url == JWKS_URL
    assert auth.required_scope == "ai-capture"
    assert auth.clock_skew_seconds == 0
    assert resolved == [config["registry_url"]]
    config["m2m"]["required_scope"] = "ai-agent"
    assert m2m_from_config(config).required_scope == "ai-agent"