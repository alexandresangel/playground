#!/usr/bin/env python3
"""Opt-in integration checks against a running Capture HTTP API.

Run with ``uv run --locked python tests/test_integ.py [path/to/test.api.json]``.
Like ai-agent, configuration comes from INTEG_PLATFORM_CONFIG + INTEG_APP_CONFIG,
the legacy SMOKE_API_CONFIG JSON blob, or tests/test.api.json, in that order.
ACA_DEPLOY_URL / CAPTURE_URL override capture_url. PDF paths may be relative to
the config file, repository root, or tests/. The bundled PDF is the default;
ai-agent's intelligence_contract_pdf key and test/ path prefix are also accepted.

This script always exercises PDF extraction with debug=true, so it can verify
the requested trade type before reference resolution replaces it with an ID.
Document contents and credentials are never printed. Importing this module or
running pytest does not make live requests; only direct execution does.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import httpx

# Match ai-agent's directly executable test script, including uninstalled checkouts.
_REPO_ROOT = Path(__file__).resolve().parents[1]
for _source_dir in (_REPO_ROOT / "src", _REPO_ROOT / "src/capture/common"):
    if str(_source_dir) not in sys.path:
        sys.path.insert(0, str(_source_dir))

from capture.http_contract import (
    AUTHORIZATION_HEADER, CORRELATION_HEADER, CUSTOMER_ID_HEADER,
    DIAPASON_API_JWT_HEADER, DIAPASON_BASE_URL_HEADER, DIAPASON_SCOPE_HEADER,
    LOCALE_HEADER, USER_ID_HEADER,
)
from registry_client import RegistryError, m2m_token_url_from_registry

__test__ = False  # Live checks are explicitly invoked, never collected by pytest.
TESTS_DIR = Path(__file__).resolve().parent
TIMEOUT_S = 60.0
CAPTURE_TIMEOUT_S = 600.0
_ENV_PLATFORM = "INTEG_PLATFORM_CONFIG"
_ENV_APP = "INTEG_APP_CONFIG"


class IntegrationFailure(ValueError):
    """A diagnostic containing fixed labels/status codes, safe to print in CI."""


def _json_config(raw: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise IntegrationFailure(f"{label}: invalid JSON") from None
    if not isinstance(data, dict):
        raise IntegrationFailure(f"{label}: must be a JSON object")
    return data


def _parse_json_env(name: str) -> dict[str, Any] | None:
    raw = (os.environ.get(name) or "").strip()
    return _json_config(raw, name) if raw else None


def load_config(config_path: Path | None = None) -> tuple[dict[str, Any], Path]:
    platform = _parse_json_env(_ENV_PLATFORM)
    app = _parse_json_env(_ENV_APP)
    base = TESTS_DIR
    if platform is not None or app is not None:
        data = {**(platform or {}), **(app or {})}
    elif (legacy := _parse_json_env("SMOKE_API_CONFIG")) is not None:
        data = legacy
    else:
        config_path = config_path or TESTS_DIR / "test.api.json"
        if not config_path.is_file():
            raise IntegrationFailure(
                "Missing integration config: set INTEG_PLATFORM_CONFIG + INTEG_APP_CONFIG, "
                "or copy tests/test.api.example.json to tests/test.api.json"
            )
        data = _json_config(config_path.read_text(encoding="utf-8"), "Integration config file")
        base = config_path.resolve().parent

    capture_url = (os.environ.get("ACA_DEPLOY_URL") or "").strip() or (
        os.environ.get("CAPTURE_URL") or ""
    ).strip()
    if capture_url:
        data["capture_url"] = capture_url.rstrip("/")
    for env_key, config_key in (
        ("M2M_CLIENT_ID", "m2m_client_id"),
        ("M2M_CLIENT_SECRET", "m2m_client_secret"),
        ("M2M_TOKEN_URL", "m2m_token_url"),
        ("REGISTRY_URL", "registry_url"),
    ):
        value = (os.environ.get(env_key) or "").strip()
        if value:
            data[config_key] = value
    return data, base


def required(config: dict, key: str) -> str:
    value = str(config.get(key) or "").strip()
    if not value:
        raise IntegrationFailure(f"Missing integration configuration: {key}")
    return value


def _int_field(config: dict, key: str) -> str:
    try:
        return str(int(config[key]))
    except (KeyError, TypeError, ValueError):
        raise IntegrationFailure(f"Integration configuration {key} must be an integer") from None


def check(response: httpx.Response, name: str) -> dict:
    if response.status_code != 200:
        raise IntegrationFailure(f"{name}: HTTP {response.status_code}, expected 200")
    try:
        body = response.json()
    except ValueError:
        raise IntegrationFailure(f"{name}: expected JSON") from None
    if not isinstance(body, dict):
        raise IntegrationFailure(f"{name}: expected a JSON object")
    return body


def _capture_token(config: dict, client: httpx.Client) -> str:
    if config.get("m2m_client_id") and config.get("m2m_client_secret"):
        token_url = str(config.get("m2m_token_url") or "").strip()
        if not token_url:
            try:
                token_url = m2m_token_url_from_registry(required(config, "registry_url"), client=client)
            except RegistryError:
                raise IntegrationFailure("Failed to resolve M2M token URL from registry") from None
        body = check(client.post(
            token_url,
            auth=httpx.BasicAuth(required(config, "m2m_client_id"), required(config, "m2m_client_secret")),
            # Match ai-agent / Tomcat AIProxy: M2M grants the client's configured scopes.
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        ), "M2M token")
        token = str(body.get("access_token") or "").strip()
        if not token:
            raise IntegrationFailure("M2M token: missing access_token")
        print("OK  M2M client_credentials")
        return token
    return required(config, "capture_jwt_token")


def _diapason_token(config: dict, client: httpx.Client) -> str:
    client_id = str(config.get("diapason_client_id") or config.get("client_id") or "").strip()
    client_secret = str(config.get("diapason_client_secret") or config.get("client_secret") or "").strip()
    if client_id and client_secret:
        response = client.post(required(config, "diapason_base_url").rstrip("/") + "/api/login", data={
            "client_id": client_id, "client_secret": client_secret, "locale": "en_US",
        })
        if response.status_code != 200:
            raise IntegrationFailure(f"Diapason login: HTTP {response.status_code}")
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            raise IntegrationFailure("Diapason login: expected XML") from None
        token = (root.get("apiToken") or root.get("token") or "").strip()
        if not token:
            raise IntegrationFailure("Diapason login: missing apiToken")
        print("OK  Diapason login")
        return token
    return required(config, "diapason_api_jwt_token")


def check_health(client: httpx.Client, url: str) -> None:
    response = client.get(url + "/health")
    route = "/health"
    if response.status_code != 200:
        route = "/api/health"
        response = client.get(url + route)
    health = check(response, "GET " + route)
    if health.get("status") != "ok" or not {"build_date", "revision", "release"} <= health.keys():
        raise IntegrationFailure(f"GET {route}: missing build identity or unhealthy")
    if not str(health.get("revision") or "").strip():
        raise IntegrationFailure(f"GET {route}: missing revision")
    revision = (os.environ.get("EXPECTED_REVISION") or os.environ.get("IMAGE_TAG") or "").strip()
    if revision and health["revision"] != revision:
        raise IntegrationFailure(f"GET {route}: deployed revision does not match")
    if "RELEASE_TAG" in os.environ and health["release"] != os.environ["RELEASE_TAG"]:
        raise IntegrationFailure(f"GET {route}: deployed release does not match")
    print(f"OK  GET {route} (health and build identity)")


def check_metadata(client: httpx.Client, url: str, auth: dict) -> dict:
    metadata = check(client.get(url + "/api/capture", headers=auth), "GET /api/capture")
    if set(metadata) != {"enabled", "trade_types", "prompt_version"}:
        raise IntegrationFailure("GET /api/capture: unexpected metadata fields")
    if metadata["enabled"] is not True:
        raise IntegrationFailure("GET /api/capture: Capture is disabled")
    trade_types = metadata["trade_types"]
    if not isinstance(trade_types, list) or not trade_types or any(
        not isinstance(value, str) or not value.strip() for value in trade_types
    ):
        raise IntegrationFailure("GET /api/capture: expected non-empty trade_types array")
    if not isinstance(metadata["prompt_version"], str) or not metadata["prompt_version"].strip():
        raise IntegrationFailure("GET /api/capture: missing prompt_version")
    print("OK  GET /api/capture (trade types and prompt version)")
    return metadata


def _pdf_path(config: dict, base: Path) -> Path:
    raw = str(config.get("capture_pdf") or config.get("intelligence_contract_pdf")
              or "fixtures/sample-loan-contract.pdf").strip()
    path = Path(raw)
    candidates = (base / path, path, TESTS_DIR.parent / path, TESTS_DIR / path)
    if path.parts and path.parts[0] == "test":
        candidates += (TESTS_DIR.joinpath(*path.parts[1:]),)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise IntegrationFailure("Missing capture_pdf file; paths are relative to the config file, repo root, or tests/")


def _trade_types(xml: str, label: str) -> list[ET.Element]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise IntegrationFailure(f"{label}: invalid XML") from None
    return [element for element in root.iter() if element.tag.rsplit("}", 1)[-1].lower() == "tradetype"]


def check_capture_result(result: dict, trade_type: str) -> None:
    resolved_xml = result.get("trade_xml")
    if result.get("success") is not True or not isinstance(resolved_xml, str) or not resolved_xml.strip():
        raise IntegrationFailure("Capture extraction did not produce resolved XML")
    if not _trade_types(resolved_xml, "Resolved trade_xml"):
        raise IntegrationFailure("Resolved trade_xml has no tradeType element")
    debug = result.get("debug")
    source = ""
    if isinstance(debug, dict):
        for key in ("extract", "resolve_references_request"):
            detail = debug.get(key)
            if isinstance(detail, dict) and isinstance(detail.get("trade_xml"), str):
                source = detail["trade_xml"].strip()
                if source:
                    break
    if not source:
        raise IntegrationFailure("Capture debug response missing source trade_xml")
    if not any(element.get("shortname") == trade_type or (element.text or "").strip() == trade_type
               for element in _trade_types(source, "Source trade_xml")):
        raise IntegrationFailure("Source trade_xml does not contain the requested trade_type")
    if "tool_trace" in result or "timings_ms" in result:
        raise IntegrationFailure("Capture returned legacy tracing fields")


def run_integration(config: dict, base: Path, client: httpx.Client) -> None:
    url = required(config, "capture_url").rstrip("/")
    trade_type = required(config, "trade_type")
    pdf = _pdf_path(config, base)
    headers = {
        DIAPASON_SCOPE_HEADER: _int_field(config, "diapason_scope"),
        DIAPASON_BASE_URL_HEADER: required(config, "diapason_base_url").rstrip("/"),
        USER_ID_HEADER: _int_field(config, "diapason_user_id"),
        CUSTOMER_ID_HEADER: _int_field(config, "diapason_customer_id"),
        LOCALE_HEADER: "en_US", CORRELATION_HEADER: "capture-integ", "Accept": "application/json",
    }
    auth = {AUTHORIZATION_HEADER: f"Bearer {_capture_token(config, client)}"}
    check_health(client, url)
    headers.update(auth)
    headers[DIAPASON_API_JWT_HEADER] = _diapason_token(config, client)
    metadata = check_metadata(client, url, auth)
    if trade_type not in metadata["trade_types"]:
        raise IntegrationFailure("Configured trade_type is not in the Capture catalog")
    if client.get(url + "/api/capture").status_code not in (401, 403):
        raise IntegrationFailure("GET /api/capture: missing-token request was not rejected")
    print("OK  GET /api/capture rejects missing Bearer token")
    with pdf.open("rb") as pdf_file:
        response = client.post(
            url + "/api/capture", headers=headers,
            data={"trade_type": trade_type, "debug": "true"},
            files={"pdf": (pdf.name, pdf_file, "application/pdf")}, timeout=CAPTURE_TIMEOUT_S,
        )
    check_capture_result(check(response, "POST /api/capture"), trade_type)
    if response.headers.get(CORRELATION_HEADER) != "capture-integ":
        raise IntegrationFailure("Capture did not preserve correlation")
    print("OK  POST /api/capture (PDF extraction, source trade type, resolved XML, correlation)")
    print("All Capture integration checks passed.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=Path, help="API config JSON (default: tests/test.api.json)")
    args = parser.parse_args(argv)
    try:
        config, base = load_config(args.config)
        with httpx.Client(timeout=TIMEOUT_S, follow_redirects=False) as client:
            run_integration(config, base, client)
    except IntegrationFailure as exc:
        raise SystemExit(str(exc)) from None
    except (ValueError, OSError, KeyError, ET.ParseError, httpx.HTTPError) as exc:
        # Exception messages may include URLs with credentials or document content.
        raise SystemExit(f"Capture integration failed ({type(exc).__name__}); check config and service logs") from None


if __name__ == "__main__":
    main()
