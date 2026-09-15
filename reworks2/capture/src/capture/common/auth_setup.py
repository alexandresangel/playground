"""JWT auth (secrets from config JSON + env)."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from dia_jwt import JwtAuth
from dia_jwt.fastapi import jwt_deps

from settings import load_config

KEYSTORE_PATH = "jwt_keystore.p12"
KEYSTORE_ENV = "JWT_KEYSTORE_P12_B64"
ISSUER = "diapason-agent"
REVOCATION_PATH = "data/jwt_revoked.json"


def _normalize_revoked(raw: object) -> dict[str, dict]:
    if not isinstance(raw, dict):
        raise ValueError("revocation JSON root must be an object")
    jtis = raw.get("jtis", {})
    subs = raw.get("subs", {})
    if not isinstance(jtis, dict) or not isinstance(subs, dict):
        raise ValueError("revocation JSON must have object fields 'jtis' and 'subs'")
    return {"jtis": jtis, "subs": subs}


def _init_revocation_file(path: Path, config: Dict[str, Any]) -> None:
    if path.is_file():
        return
    jwt = config.get("jwt") if isinstance(config.get("jwt"), dict) else {}
    seed = jwt.get("revoked")
    if seed is not None:
        data = _normalize_revoked(seed)
    else:
        data = {"jtis": {}, "subs": {}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def build_jwt_auth(base_dir: Path, config: Dict[str, Any]) -> JwtAuth:
    jwt = config.get("jwt") if isinstance(config.get("jwt"), dict) else {}
    password = str(jwt.get("keystore_password", "") or "").strip()
    if not password:
        raise RuntimeError("Missing jwt.keystore_password in config.")
    rev_path = base_dir / REVOCATION_PATH
    _init_revocation_file(rev_path, config)

    b64 = os.getenv(KEYSTORE_ENV, "").strip()
    if b64:
        return JwtAuth(
            keystore_password=password,
            keystore_bytes=base64.b64decode(b64),
            issuer=ISSUER,
            revocation_path=rev_path,
        )

    path = base_dir / KEYSTORE_PATH
    if not path.is_file():
        raise RuntimeError(
            f"Set {KEYSTORE_ENV} (base64 PKCS#12) or place {KEYSTORE_PATH} in the app root."
        )
    return JwtAuth(
        path,
        password,
        issuer=ISSUER,
        revocation_path=rev_path,
    )


def configure_auth(base_dir: Path, config: Dict[str, Any] | None = None) -> Tuple[JwtAuth, Callable, Callable, Callable, Callable]:
    cfg = config or load_config()
    auth = build_jwt_auth(base_dir, cfg)
    deps = jwt_deps(auth)
    return (
        auth,
        deps["get_identity"],
        deps["require_admin"],
        deps["require_refresh"],
        deps["require_chat"],
    )
