#!/usr/bin/env python3
"""Export one PDF's raw Capture response and XML, using integration-test config.

    uv run --locked python scripts/capture_pdf.py

Uses INTEG_PLATFORM_CONFIG + INTEG_APP_CONFIG, SMOKE_API_CONFIG, or a config file.
Uses capture_pdf and trade_type from config; --pdf and --trade-type override them.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from uuid import uuid4
import xml.etree.ElementTree as ET

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _source_dir in (_REPO_ROOT, _REPO_ROOT / "src", _REPO_ROOT / "src/capture/common"):
    if str(_source_dir) not in sys.path:
        sys.path.insert(0, str(_source_dir))

from capture.http_contract import (
    AUTHORIZATION_HEADER, CORRELATION_HEADER, CUSTOMER_ID_HEADER,
    DIAPASON_API_JWT_HEADER, DIAPASON_BASE_URL_HEADER, DIAPASON_SCOPE_HEADER,
    LOCALE_HEADER, USER_ID_HEADER,
)
from evals.artifacts import save_response
from registry_client import RegistryError, m2m_token_url_from_registry

TESTS_DIR = _REPO_ROOT / "tests"
RESPONSES_DIR = _REPO_ROOT / "evals/responses"
TIMEOUT_S = 60.0
CAPTURE_TIMEOUT_S = 600.0
_ENV_PLATFORM = "INTEG_PLATFORM_CONFIG"
_ENV_APP = "INTEG_APP_CONFIG"


class ExportFailure(ValueError):
    """A fixed diagnostic safe to print without exposing credentials or responses."""


# Keep this config/auth flow aligned with tests/test_integ.py, without importing
# or changing the existing integration script.
def _json_config(raw: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ExportFailure(f"{label}: invalid JSON") from None
    if not isinstance(data, dict):
        raise ExportFailure(f"{label}: must be a JSON object")
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
            raise ExportFailure(
                "Missing integration config: set INTEG_PLATFORM_CONFIG + INTEG_APP_CONFIG, "
                "or copy tests/test.api.example.json to tests/test.api.json"
            )
        data = _json_config(config_path.read_text(encoding="utf-8"), "Integration config file")
        base = config_path.resolve().parent
    # Deploy overrides capture_url to the just-deployed ACA URL.
    capture_url = (os.environ.get("ACA_DEPLOY_URL") or "").strip() or (
        os.environ.get("CAPTURE_URL") or ""
    ).strip()
    if capture_url:
        data["capture_url"] = capture_url.rstrip("/")
    # Optional env overrides for m2m client_credentials (CI / local).
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
        raise ExportFailure(f"Missing integration configuration: {key}")
    return value


def _int_field(config: dict, key: str) -> str:
    try:
        return str(int(config[key]))
    except (KeyError, TypeError, ValueError):
        raise ExportFailure(f"Integration configuration {key} must be an integer") from None


def check(response: httpx.Response, name: str) -> dict:
    if response.status_code != 200:
        raise ExportFailure(f"{name}: HTTP {response.status_code}, expected 200")
    try:
        body = response.json()
    except ValueError:
        raise ExportFailure(f"{name}: expected JSON") from None
    if not isinstance(body, dict):
        raise ExportFailure(f"{name}: expected a JSON object")
    return body


def _capture_token(config: dict, client: httpx.Client) -> str:
    if config.get("m2m_client_id") and config.get("m2m_client_secret"):
        token_url = str(config.get("m2m_token_url") or "").strip()
        if not token_url:
            try:
                token_url = m2m_token_url_from_registry(required(config, "registry_url"), client=client)
            except RegistryError:
                raise ExportFailure("Failed to resolve M2M token URL from registry") from None
        body = check(client.post(
            token_url,
            auth=httpx.BasicAuth(required(config, "m2m_client_id"), required(config, "m2m_client_secret")),
            # Match ai-agent / Tomcat AIProxy: M2M grants the client's configured scopes.
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        ), "M2M token")
        token = str(body.get("access_token") or "").strip()
        if not token:
            raise ExportFailure("M2M token: missing access_token")
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
            raise ExportFailure(f"Diapason login: HTTP {response.status_code}")
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            raise ExportFailure("Diapason login: expected XML") from None
        token = (root.get("apiToken") or root.get("token") or "").strip()
        if not token:
            raise ExportFailure("Diapason login: missing apiToken")
        print("OK  Diapason login")
        return token
    return required(config, "diapason_api_jwt_token")


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
    raise ExportFailure("Missing capture_pdf file; paths are relative to the config file, repo root, or tests/")


def run_export(
    config: dict, base: Path, client: httpx.Client, *, output_dir: Path | None = None,
    capture_timeout_s: float = CAPTURE_TIMEOUT_S,
) -> Path:
    if not math.isfinite(capture_timeout_s) or capture_timeout_s <= 0:
        raise ExportFailure("Capture timeout must be a positive finite number")
    url = required(config, "capture_url").rstrip("/")
    trade_type = required(config, "trade_type")
    pdf = _pdf_path(config, base)
    try:
        pdf_bytes = pdf.read_bytes()
    except OSError:
        raise ExportFailure("Cannot read input PDF") from None
    correlation = "capture-export-" + uuid4().hex
    headers = {
        DIAPASON_SCOPE_HEADER: _int_field(config, "diapason_scope"),
        DIAPASON_BASE_URL_HEADER: required(config, "diapason_base_url").rstrip("/"),
        USER_ID_HEADER: _int_field(config, "diapason_user_id"),
        CUSTOMER_ID_HEADER: _int_field(config, "diapason_customer_id"),
        LOCALE_HEADER: "en_US", CORRELATION_HEADER: correlation, "Accept": "application/json",
    }
    if output_dir is None:
        stem = re.sub(r"[^A-Za-z0-9_-]+", "-", pdf.stem).strip("-")[:80] or "capture"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = RESPONSES_DIR / f"{stem}-{stamp}-{uuid4().hex[:8]}"
    output_dir = Path(output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ExportFailure("Output directory already exists; choose a fresh path") from None
    except OSError:
        raise ExportFailure("Cannot create fresh output directory") from None
    print(f"Artifacts: {output_dir.resolve()}", flush=True)
    started = time.perf_counter()
    run: dict[str, Any] = {
        "schema_version": 1, "started_at": datetime.now(timezone.utc).isoformat(),
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(), "trade_type": trade_type,
        "correlation_id": correlation, "status_code": None, "success": False,
        "error": None, "error_category": None, "artifacts": {},
    }
    phase = "authentication"
    try:
        headers[AUTHORIZATION_HEADER] = f"Bearer {_capture_token(config, client)}"
        headers[DIAPASON_API_JWT_HEADER] = _diapason_token(config, client)
        print(f"-> POST /api/capture pdf={pdf} trade_type={trade_type!r} timeout={capture_timeout_s:g}s", flush=True)
        response = client.post(
            url + "/api/capture", headers=headers,
            data={"trade_type": trade_type, "debug": "true"},
            files={"pdf": (pdf.name, pdf_bytes, "application/pdf")}, timeout=capture_timeout_s,
        )
        run["status_code"] = response.status_code
        # Save original bytes before validating HTTP/business status or XML.
        run.update(save_response(response, output_dir))
        phase = "http" if response.status_code != 200 else "protocol"
        result = check(response, "POST /api/capture")
        if result.get("success") is not True:
            phase = "business"
            raise ExportFailure("Capture extraction did not succeed; inspect the saved response")
        xml = result.get("trade_xml")
        if not isinstance(xml, str) or not xml.strip():
            raise ExportFailure("Capture response is missing resolved trade_xml")
        try:
            ET.fromstring(xml)
        except ET.ParseError:
            raise ExportFailure("Resolved trade_xml is invalid XML") from None
        run["success"] = True
        print("OK  Saved raw response and resolved XML")
        return output_dir
    except ExportFailure as exc:
        run.update(error=str(exc), error_category=phase)
        raise
    except (httpx.HTTPError, httpx.InvalidURL):
        run.update(error="HTTP request failed; check connectivity and service logs", error_category="transport")
        raise
    except OSError:
        run.update(error="Cannot write capture artifacts", error_category="artifacts")
        raise
    finally:
        run["duration_seconds"] = round(time.perf_counter() - started, 6)
        try:
            (output_dir / "run.json").write_text(
                json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
            )
        except OSError:
            raise ExportFailure("Cannot write capture run metadata") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=Path, help="API config JSON (default: tests/test.api.json)")
    parser.add_argument("--config", dest="config_option", type=Path, help="Alias for the positional config path")
    parser.add_argument("--pdf", type=Path, help="Override capture_pdf (relative to the working directory)")
    parser.add_argument("--trade-type", help="Override the configured catalog trade type")
    parser.add_argument("--output", type=Path, help="New output directory (default: evals/responses/<PDF>-<UTC>-<unique ID>)")
    parser.add_argument("--timeout", type=float, default=CAPTURE_TIMEOUT_S, help="Capture timeout in seconds (default: 600)")
    args = parser.parse_args(argv)
    if args.config is not None and args.config_option is not None:
        parser.error("Provide the config path either positionally or with --config")
    try:
        config, base = load_config(args.config_option or args.config)
        if args.pdf is not None:
            config["capture_pdf"] = str(args.pdf.resolve())
        if args.trade_type is not None:
            config["trade_type"] = args.trade_type
        with httpx.Client(timeout=TIMEOUT_S, follow_redirects=False) as client:
            run_export(config, base, client, output_dir=args.output, capture_timeout_s=args.timeout)
    except ExportFailure as exc:
        print(f"Capture export failed: {exc}", file=sys.stderr)
        return 1
    except (ValueError, OSError, KeyError, ET.ParseError, httpx.HTTPError, httpx.InvalidURL) as exc:
        # Exception text may contain URLs with credentials or document content.
        print(f"Capture export failed ({type(exc).__name__}); check config and service logs", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
