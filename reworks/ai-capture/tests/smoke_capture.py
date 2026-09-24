"""Opt-in live Capture smoke checks; never collected by offline pytest.

Run: uv run python tests/smoke_capture.py [tests/test.api.local.json]
Deployment supplies SMOKE_API_CONFIG and ACA_DEPLOY_URL/CAPTURE_URL.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from capture.http_contract import (
    AUTHORIZATION_HEADER, CORRELATION_HEADER, CUSTOMER_ID_HEADER,
    DIAPASON_API_JWT_HEADER, DIAPASON_BASE_URL_HEADER, DIAPASON_SCOPE_HEADER,
    LOCALE_HEADER, USER_ID_HEADER,
)
from registry_client import m2m_token_url_from_registry

TESTS_DIR = Path(__file__).resolve().parent

_ENV_PLATFORM = "INTEG_PLATFORM_CONFIG"
_ENV_APP = "INTEG_APP_CONFIG"


class SmokeFailure(ValueError):
    """A diagnostic built from fixed labels/status codes, safe to print in CI."""


def _parse_json_env(name: str) -> dict[str, Any] | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {name}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{name} must be a JSON object.")
    return data


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    platform = _parse_json_env(_ENV_PLATFORM)
    app = _parse_json_env(_ENV_APP)

    if platform is not None or app is not None:
        data = {**(platform or {}), **(app or {})}
        base = TESTS_DIR  # Path(f"<env:{_ENV_PLATFORM}+{_ENV_APP}>")
    else:
        config_path = config_path or TESTS_DIR / "test.api.json"
        if not config_path.is_file():
            raise SystemExit(
                f"Missing {config_path} (or set {_ENV_PLATFORM}+{_ENV_APP}). "
                "Copy tests/integ.platform.example.json + "
                "tests/integ.app.example.json (or test.api.example.json)."
            )
        data = json.loads(config_path.read_text(encoding="utf-8"))
        base = config_path.resolve().parent
    if not isinstance(data, dict):
        raise SystemExit("smoke config must be a JSON object.")
    # Deploy overrides capture_url to the just-deployed ACA URL.
    capture_url = (
        (os.environ.get("ACA_DEPLOY_URL") or "").strip()
        or (os.environ.get("CAPTURE_URL") or "").strip()
    )
    if capture_url:
        data["capture_url"] = capture_url.rstrip("/")
    # Optional env overrides for m2m client_credentials (CI / local).
    for env_key, cfg_key in (
        ("M2M_CLIENT_ID", "m2m_client_id"),
        ("M2M_CLIENT_SECRET", "m2m_client_secret"),
        ("M2M_TOKEN_URL", "m2m_token_url"),
        ("REGISTRY_URL", "registry_url"),
    ):
        env_val = (os.environ.get(env_key) or "").strip()
        if env_val:
            data[cfg_key] = env_val
    return data, base


def required(config: dict, key: str) -> str:
    value = str(config.get(key) or "").strip()
    if not value:
        raise SmokeFailure(f"Missing smoke configuration: {key}")
    return value


def check(response: httpx.Response, name: str) -> dict:
    if response.status_code != 200:
        # Responses may contain credentials or document content; do not print them.
        raise SmokeFailure(f"{name}: HTTP {response.status_code}, expected 200")
    try:
        body = response.json()
    except ValueError as exc:
        raise SmokeFailure(f"{name}: expected JSON") from exc
    if not isinstance(body, dict):
        raise SmokeFailure(f"{name}: expected a JSON object")
    return body


def run_smoke(config: dict, base: Path, client: httpx.Client) -> None:
    url = required(config, "capture_url").rstrip("/")
    for route in ("/health", "/api/health"):
        health = check(client.get(url + route), route)
        if health.get("status") != "ok" or not {"build_date", "revision", "release"} <= health.keys():
            raise SmokeFailure(f"{route}: missing build identity or unhealthy")
        revision = os.getenv("EXPECTED_REVISION") or os.getenv("IMAGE_TAG")
        if revision and health["revision"] != revision:
            raise SmokeFailure(f"{route}: deployed revision does not match")
        if "RELEASE_TAG" in os.environ and health["release"] != os.environ["RELEASE_TAG"]:
            raise SmokeFailure(f"{route}: deployed release does not match")

    token = str(config.get("capture_jwt_token") or "").strip()
    if config.get("m2m_client_id") and config.get("m2m_client_secret"):
        token_url = config.get("m2m_token_url") or m2m_token_url_from_registry(
            required(config, "registry_url"), client=client,
        )
        body = check(client.post(
            token_url, auth=httpx.BasicAuth(required(config, "m2m_client_id"), required(config, "m2m_client_secret")),
            data={"grant_type": "client_credentials", "scope": "ai-capture"},
        ), "M2M token")
        token = required(body, "access_token")
    if not token:
        raise SmokeFailure("Set capture_jwt_token or M2M client credentials")
    auth = {AUTHORIZATION_HEADER: f"Bearer {token}"}
    check(client.post(url + "/api/refresh-prompt", headers=auth), "Refresh prompts")
    metadata = check(client.get(url + "/api/capture", headers=auth), "Capture metadata")
    if metadata.get("enabled") is not True:
        raise SmokeFailure("Capture is disabled")
    for route in ("/api/capture", "/api/skills/intelligence-contract"):
        if client.get(url + route).status_code not in (401, 403):
            raise SmokeFailure(f"{route}: missing-token request was not rejected")

    api_token = str(config.get("diapason_api_jwt_token") or "").strip()
    if config.get("diapason_client_id") and config.get("diapason_client_secret"):
        response = client.post(required(config, "diapason_base_url").rstrip("/") + "/api/login", data={
            "client_id": required(config, "diapason_client_id"),
            "client_secret": required(config, "diapason_client_secret"), "locale": "en_US",
        })
        if response.status_code != 200:
            raise SmokeFailure(f"Diapason login: HTTP {response.status_code}")
        root = ET.fromstring(response.text)
        api_token = root.get("apiToken") or root.get("token") or ""
    if not api_token:
        raise SmokeFailure("Set diapason_api_jwt_token or Diapason client credentials")
    headers = {
        **auth, DIAPASON_API_JWT_HEADER: api_token,
        DIAPASON_SCOPE_HEADER: str(int(config["diapason_scope"])),
        DIAPASON_BASE_URL_HEADER: required(config, "diapason_base_url"),
        USER_ID_HEADER: str(int(config["diapason_user_id"])),
        CUSTOMER_ID_HEADER: str(int(config["diapason_customer_id"])),
        LOCALE_HEADER: "en_US", CORRELATION_HEADER: "capture-smoke",
    }
    pdf = base / str(config.get("capture_pdf") or "fixtures/sample-loan-contract.pdf")
    response = client.post(url + "/api/capture", headers=headers,
        data={"trade_type": str(config.get("trade_type") or "iamLoan"), "debug": "false"},
        files={"pdf": (pdf.name, pdf.read_bytes(), "application/pdf")}, timeout=600,
    )
    result = check(response, "Capture extraction")
    if result.get("success") is not True or not result.get("trade_xml"):
        raise SmokeFailure("Capture extraction did not produce resolved XML")
    ET.fromstring(result["trade_xml"])
    if "tool_trace" in result or "timings_ms" in result:
        raise SmokeFailure("Capture returned legacy tracing fields")
    if response.headers.get(CORRELATION_HEADER) != "capture-smoke":
        raise SmokeFailure("Capture did not preserve correlation")
    print("Capture smoke passed: health, identity, auth, catalog, PDF extraction, correlation")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        config, base = load_config(args.config)
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            run_smoke(config, base, client)
    except SmokeFailure as exc:
        raise SystemExit(str(exc)) from None
    except (ValueError, OSError, KeyError, ET.ParseError, httpx.HTTPError) as exc:
        # Avoid HTTP exception URLs, request bodies, and XML content in CI output.
        raise SystemExit(f"Capture smoke failed ({type(exc).__name__}); check config and service logs") from None


if __name__ == "__main__":
    main()