"""Live Capture smoke: uv run python tests/smoke_capture.py [config path].

Uses SMOKE_API_CONFIG JSON or tests/test.api.json. CAPTURE_URL overrides the
configured URL. A configured capture_pdf enables the real model/MCP extraction.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import httpx

from registry_client import m2m_token_url_from_registry


def required(config: dict, key: str) -> str:
    value = str(config.get(key, "") or "").strip()
    if not value:
        raise RuntimeError(f"Missing smoke config: {key}")
    return value


def response_json(response: httpx.Response, operation: str) -> dict:
    if response.status_code != 200:
        raise RuntimeError(f"{operation}: HTTP {response.status_code}")
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError(f"{operation}: expected a JSON object")
    return body


def access_token(config: dict, client: httpx.Client) -> str:
    client_id = config.get("m2m_client_id")
    client_secret = config.get("m2m_client_secret")
    if not (client_id and client_secret):
        return required(config, "capture_access_token")
    token_url = str(config.get("m2m_token_url") or "").strip()
    if not token_url:
        token_url = m2m_token_url_from_registry(required(config, "registry_url"), client=client)
    # Match AIProxy: Basic auth and no scope parameter; M2M grants client scopes.
    response = client.post(token_url, auth=httpx.BasicAuth(client_id, client_secret),
                           data={"grant_type": "client_credentials"}, headers={"Accept": "application/json"})
    return required(response_json(response, "M2M token"), "access_token")


def diapason_token(config: dict, client: httpx.Client) -> str:
    client_id = config.get("diapason_client_id") or config.get("client_id")
    client_secret = config.get("diapason_client_secret") or config.get("client_secret")
    if not (client_id and client_secret):
        return required(config, "diapason_api_jwt_token")
    url = required(config, "diapason_base_url").rstrip("/") + "/api/login"
    response = client.post(url, data={"client_id": client_id, "client_secret": client_secret, "locale": "en_US"})
    if response.status_code != 200:
        raise RuntimeError(f"Diapason login: HTTP {response.status_code}")
    root = ET.fromstring(response.text)
    token = root.get("apiToken") or root.get("token")
    if not token:
        raise RuntimeError("Diapason login: missing apiToken")
    return token


def run_smoke(config: dict, client: httpx.Client, config_dir: Path) -> None:
    base = required(config, "capture_url").rstrip("/")
    for path in ("/health", "/api/health"):
        body = response_json(client.get(base + path), path)
        if body.get("status") != "ok":
            raise RuntimeError(f"{path}: service is not healthy")
        for field in ("version", "revision"):
            expected = os.environ.get("EXPECTED_" + field.upper())
            if expected and body.get(field) != expected:
                raise RuntimeError(f"{path}: unexpected {field}")
    print("OK health and build identity")
    if client.get(base + "/api/capture").status_code not in (401, 403):
        raise RuntimeError("Capture metadata must require authentication")
    headers = {"Authorization": "Bearer " + access_token(config, client)}
    metadata = response_json(client.get(base + "/api/capture", headers=headers), "Capture metadata")
    if metadata.get("enabled") is not True or not metadata.get("trade_types") or not metadata.get("prompt_version"):
        raise RuntimeError("Capture metadata: missing enabled catalog")
    print("OK M2M authentication and Capture catalog")
    pdf_name = str(config.get("capture_pdf") or "").strip()
    if not pdf_name:
        print("SKIP extraction (set capture_pdf and trade_type to exercise model + MCP)")
        return
    pdf = Path(pdf_name)
    if not pdf.is_absolute():
        pdf = config_dir / pdf
    trade_type = required(config, "trade_type")
    if trade_type not in metadata["trade_types"]:
        raise RuntimeError("Smoke trade_type is not in the Capture catalog")
    headers.update({
        "X-Diapason-User-Id": required(config, "diapason_user_id"),
        "X-Diapason-Customer-Id": required(config, "diapason_customer_id"),
        "X-Diapason-Mcp-Token": diapason_token(config, client),
        "X-Diapason-Mcp-Scope": required(config, "diapason_scope"),
        "X-Diapason-Mcp-Base-Url": required(config, "diapason_base_url"),
        "X-Diapason-Chat-Session": "capture-smoke",
    })
    with pdf.open("rb") as file:
        response = client.post(base + "/api/capture", headers=headers,
                               data={"trade_type": trade_type, "debug": "false"},
                               files={"pdf": (pdf.name, file, "application/pdf")}, timeout=600)
    result = response_json(response, "Capture extraction")
    if result.get("success") is not True or not result.get("trade_xml"):
        raise RuntimeError("Capture extraction did not resolve trade XML")
    ET.fromstring(result["trade_xml"])
    if response.headers.get("X-Diapason-Chat-Session") != "capture-smoke":
        raise RuntimeError("Capture extraction lost the correlation ID")
    if "session_artifacts" in result or "timings_ms" in result:
        raise RuntimeError("Capture extraction leaked internal/session fields")
    print("OK PDF extraction, reference resolution and correlation (no trade import)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=Path, default=Path(__file__).with_name("test.api.json"))
    args = parser.parse_args()
    raw = os.environ.get("SMOKE_API_CONFIG", "").strip() or args.config.read_text(encoding="utf-8")
    config = json.loads(raw)
    if not isinstance(config, dict):
        raise SystemExit("Smoke config must be a JSON object")
    for env, key in (("CAPTURE_URL", "capture_url"), ("M2M_CLIENT_ID", "m2m_client_id"),
                     ("M2M_CLIENT_SECRET", "m2m_client_secret"), ("M2M_TOKEN_URL", "m2m_token_url"),
                     ("REGISTRY_URL", "registry_url")):
        if os.environ.get(env, "").strip():
            config[key] = os.environ[env].strip()
    try:
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            run_smoke(config, client, args.config.resolve().parent)
    except httpx.HTTPError as exc:
        raise SystemExit(f"Smoke network failure ({type(exc).__name__})") from None
    except (RuntimeError, ValueError, OSError, ET.ParseError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
