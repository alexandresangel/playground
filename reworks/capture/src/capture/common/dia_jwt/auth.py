"""RS256 JWT auth: PKCS#12 keystore, mint, validate, revoke."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID


class TokenValidationError(Exception):
    pass


class JwtAuth:
    def __init__(
        self,
        keystore_path: Optional[Union[str, Path]] = None,
        keystore_password: str = "",
        *,
        keystore_bytes: Optional[bytes] = None,
        issuer: str = "diapason-agent",
        revocation_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self.issuer = issuer
        self._password = keystore_password
        if keystore_bytes is not None:
            self._p12_data = keystore_bytes
            rev_default = Path("data/jwt_revoked.json")
        elif keystore_path is not None:
            p12 = Path(keystore_path)
            if not p12.is_file():
                raise FileNotFoundError(f"JWT keystore not found: {p12}")
            self._p12_data = p12.read_bytes()
            rev_default = p12.parent / "jwt_revoked.json"
        else:
            raise ValueError("keystore_path or keystore_bytes is required")
        rev = Path(revocation_path) if revocation_path else rev_default
        self._revoked_path = rev
        self._lock = threading.Lock()
        rev.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create_keystore(cls, path: Union[str, Path], password: str, **kwargs: Any) -> JwtAuth:
        p = Path(path)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Diapason"),
                x509.NameAttribute(NameOID.COMMON_NAME, "dia-jwt"),
            ]
        )
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=3650))
            .sign(key, hashes.SHA256())
        )
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(
            pkcs12.serialize_key_and_certificates(
                name=b"dia-jwt",
                key=key,
                cert=cert,
                cas=None,
                encryption_algorithm=BestAvailableEncryption(password.encode()),
            )
        )
        return cls(p, password, **kwargs)

    def _keys(self):
        key, cert, _ = pkcs12.load_key_and_certificates(
            self._p12_data, self._password.encode()
        )
        if key is None or cert is None:
            raise ValueError("Keystore must contain private key and certificate")
        return key, cert.public_key()

    def _sign(self, payload: Dict[str, Any]) -> str:
        private_key, _ = self._keys()
        return jwt.encode(payload, private_key, algorithm="RS256")

    def _verify(self, token: str) -> Dict[str, Any]:
        _, public_key = self._keys()
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=self.issuer,
            options={"require": ["exp", "iat"]},
        )

    def _revoked(self) -> Dict[str, dict]:
        if not self._revoked_path.is_file():
            return {"jtis": {}, "subs": {}}
        try:
            raw = json.loads(self._revoked_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"jtis": {}, "subs": {}}
        if not isinstance(raw, dict):
            return {"jtis": {}, "subs": {}}
        raw.setdefault("jtis", {})
        raw.setdefault("subs", {})
        return raw

    def _save_revoked(self, data: Dict[str, dict]) -> None:
        self._revoked_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _is_revoked(self, jti: Optional[str], sub: Optional[str]) -> bool:
        with self._lock:
            data = self._revoked()
            if sub and sub in data["subs"]:
                return True
            return bool(jti and jti in data["jtis"])

    def mint(
        self,
        *,
        sub: str,
        roles: Sequence[str],
        customer_id: Optional[int] = None,
        ttl_days: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not sub or not roles:
            raise ValueError("sub and roles are required")
        now = datetime.now(timezone.utc)
        if ttl_seconds is not None:
            exp = now + timedelta(seconds=int(ttl_seconds))
        elif ttl_days is not None:
            exp = now + timedelta(days=int(ttl_days))
        else:
            exp = now + timedelta(days=90)

        jti = str(uuid.uuid4())
        payload: Dict[str, Any] = {
            "iss": self.issuer,
            "sub": sub,
            "roles": list(roles),
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        if customer_id is not None:
            payload["customer_id"] = int(customer_id)

        token = self._sign(payload)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_at": exp.replace(microsecond=0).isoformat(),
            "jti": jti,
            "sub": sub,
            "roles": list(roles),
        }

    def validate(self, token: str, *, roles: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        try:
            claims = self._verify(token)
        except Exception as exc:
            raise TokenValidationError(f"Invalid token: {exc}") from exc

        jti = claims.get("jti") if isinstance(claims.get("jti"), str) else None
        sub = claims.get("sub") if isinstance(claims.get("sub"), str) else None
        if self._is_revoked(jti, sub):
            raise TokenValidationError("Token has been revoked")

        if roles:
            token_roles = claims.get("roles") or []
            if not isinstance(token_roles, list):
                token_roles = [token_roles]
            if not set(roles) & {str(r) for r in token_roles}:
                raise TokenValidationError("Insufficient role")
        return claims

    def revoke(self, *, jti: Optional[str] = None, sub: Optional[str] = None) -> None:
        if not jti and not sub:
            raise ValueError("jti or sub required")
        stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self._lock:
            data = self._revoked()
            if jti:
                data["jtis"][jti] = {"revoked_at": stamp}
            if sub:
                data["subs"][sub] = {"revoked_at": stamp}
            self._save_revoked(data)