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

import httpx

from capture.http_contract import (
    AUTHORIZATION_HEADER, CORRELATION_HEADER, CUSTOMER_ID_HEADER,
    DIAPASON_API_JWT_HEADER, DIAPASON_BASE_URL_HEADER, DIAPASON_SCOPE_HEADER,
    LOCALE_HEADER, USER_ID_HEADER,
)
from registry_client import m2m_token_url_from_registry

TESTS_DIR = Path(__file__).resolve().parent


class SmokeFailure(ValueError):
    """A diagnostic built from fixed labels/status codes, safe to print in CI."""


def load_config(path: Path | None = None) -> tuple[dict, Path]:
    raw = os.getenv("SMOKE_API_CONFIG", "").strip()
    if raw:
        config, base = json.loads(raw), TESTS_DIR
    else:
        local = TESTS_DIR / "test.api.local.json"
        path = path or (local if local.is_file() else TESTS_DIR / "test.api.json")
        config, base = json.loads(path.read_text(encoding="utf-8")), path.resolve().parent
    if not isinstance(config, dict):
        raise SmokeFailure("Smoke config must be a JSON object")
    for env, key in (("M2M_CLIENT_ID", "m2m_client_id"), ("M2M_CLIENT_SECRET", "m2m_client_secret"),
                     ("M2M_TOKEN_URL", "m2m_token_url"), ("REGISTRY_URL", "registry_url")):
        if os.getenv(env):
            config[key] = os.environ[env]
    override = os.getenv("ACA_DEPLOY_URL") or os.getenv("CAPTURE_URL")
    if override:
        config["capture_url"] = override.rstrip("/")
    return config, base


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
