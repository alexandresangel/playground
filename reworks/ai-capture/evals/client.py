"""Explicit HTTP capture exports, independent of tests and application startup."""

from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlsplit
import uuid
import xml.etree.ElementTree as ET

import httpx

from capture.http_contract import (
    AUTHORIZATION_HEADER, CORRELATION_HEADER, CUSTOMER_ID_HEADER,
    DIAPASON_API_JWT_HEADER, DIAPASON_BASE_URL_HEADER, DIAPASON_SCOPE_HEADER,
    LOCALE_HEADER, USER_ID_HEADER,
)
from registry_client import RegistryError, m2m_token_url_from_registry
from evals.artifacts import save_response


class ApiConfigError(ValueError):
    """Fixed-label diagnostic that does not include credentials or response bodies."""


class _AuthenticationError(ValueError):
    pass


def _json_config(raw: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except ValueError:
        raise ApiConfigError(f"{label}: invalid JSON") from None
    if not isinstance(data, dict):
        raise ApiConfigError(f"{label}: must be a JSON object")
    return data


def load_api_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load an explicit file, or integration environment JSON / fallback file.

    An explicit file takes priority over JSON environment configuration. Deployment
    URL and individual M2M environment overrides match the integration scripts.
    """
    if config_path is not None:
        try:
            data = _json_config(Path(config_path).read_text(encoding="utf-8-sig"), "API config file")
        except (OSError, UnicodeError):
            raise ApiConfigError("Cannot read API config file") from None
    else:
        platform = (os.environ.get("INTEG_PLATFORM_CONFIG") or "").strip()
        app = (os.environ.get("INTEG_APP_CONFIG") or "").strip()
        legacy = (os.environ.get("SMOKE_API_CONFIG") or "").strip()
        if platform or app:
            data = {**(_json_config(platform, "INTEG_PLATFORM_CONFIG") if platform else {}),
                    **(_json_config(app, "INTEG_APP_CONFIG") if app else {})}
        elif legacy:
            data = _json_config(legacy, "SMOKE_API_CONFIG")
        else:
            path = Path(__file__).resolve().parents[1] / "tests/test.api.json"
            try:
                data = _json_config(path.read_text(encoding="utf-8-sig"), "API config file")
            except (OSError, UnicodeError):
                raise ApiConfigError("Missing API config: use --config, INTEG_PLATFORM_CONFIG + INTEG_APP_CONFIG, or tests/test.api.json") from None
    capture_url = (os.environ.get("ACA_DEPLOY_URL") or "").strip() or (os.environ.get("CAPTURE_URL") or "").strip()
    if capture_url:
        data["capture_url"] = capture_url.rstrip("/")
    for env_key, config_key in (("M2M_CLIENT_ID", "m2m_client_id"), ("M2M_CLIENT_SECRET", "m2m_client_secret"),
                                ("M2M_TOKEN_URL", "m2m_token_url"), ("REGISTRY_URL", "registry_url")):
        value = (os.environ.get(env_key) or "").strip()
        if value:
            data[config_key] = value
    return data


def _required(config: dict, key: str) -> str:
    value = str(config.get(key) or "").strip()
    if not value:
        raise ApiConfigError(f"Missing API configuration: {key}")
    return value


def _url(config: dict, key: str) -> str:
    value = _required(config, key).rstrip("/")
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.fragment:
            raise ValueError
    except ValueError:
        raise ApiConfigError(f"API configuration {key} must be an absolute HTTP(S) URL") from None
    return value


def _integer(config: dict, key: str) -> str:
    value = config.get(key)
    try:
        if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
            raise ValueError
        return str(int(value))
    except (TypeError, ValueError):
        raise ApiConfigError(f"API configuration {key} must be an integer") from None


def _auth_json(response: httpx.Response, label: str) -> dict:
    if response.status_code != 200:
        raise _AuthenticationError(f"{label}: HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        raise _AuthenticationError(f"{label}: expected JSON") from None
    if not isinstance(body, dict):
        raise _AuthenticationError(f"{label}: expected a JSON object")
    return body


def _refresh_at(token: str, expires_in: Any = None) -> float:
    """Use expiry as a refresh hint; unverified JWT claims never grant access.

    Cap credential-backed token reuse at five minutes when expiry is missing.
    Refresh slightly early to cover the time between acquiring and using tokens.
    """
    now = time.time()
    deadline = now + 300
    try:
        lifetime = float(expires_in)
        if math.isfinite(lifetime):
            deadline = min(deadline, now + max(0, lifetime))
    except (TypeError, ValueError):
        pass
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        expiry = float(claims["exp"])
        if math.isfinite(expiry):
            deadline = min(deadline, expiry)
    except (IndexError, KeyError, TypeError, ValueError, UnicodeError):
        pass
    return max(now, deadline - min(30, max(0, deadline - now) * 0.1))


class CaptureClient:
    """Reuse authentication and HTTP connections; export each attempt separately.

    Construction and context entry are network-free. An injected httpx client is
    owned by its caller and is never closed by this class.
    """

    def __init__(self, config: dict, *, client: httpx.Client | None = None, timeout: float = 600):
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ApiConfigError("Timeout must be a positive finite number")
        self.config = dict(config)
        self.timeout = timeout
        self.url = _url(config, "capture_url")
        self._headers = {
            DIAPASON_SCOPE_HEADER: _integer(config, "diapason_scope"),
            DIAPASON_BASE_URL_HEADER: _url(config, "diapason_base_url"),
            USER_ID_HEADER: _integer(config, "diapason_user_id"),
            CUSTOMER_ID_HEADER: _integer(config, "diapason_customer_id"),
            LOCALE_HEADER: str(config.get("locale") or "en_US"), "Accept": "application/json",
        }
        m2m_id, m2m_secret = config.get("m2m_client_id"), config.get("m2m_client_secret")
        if m2m_id or m2m_secret:
            _required(config, "m2m_client_id")
            _required(config, "m2m_client_secret")
            _url(config, "m2m_token_url" if config.get("m2m_token_url") else "registry_url")
        else:
            _required(config, "capture_jwt_token")
        self._diapason_id = str(config.get("diapason_client_id") or config.get("client_id") or "").strip()
        self._diapason_secret = str(config.get("diapason_client_secret") or config.get("client_secret") or "").strip()
        if self._diapason_id or self._diapason_secret:
            if not self._diapason_id or not self._diapason_secret:
                raise ApiConfigError("Diapason client ID and secret must both be configured")
        else:
            _required(config, "diapason_api_jwt_token")
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=60, follow_redirects=False)
        self._capture_refresh_at = 0.0
        self._diapason_refresh_at = 0.0

    def __enter__(self) -> CaptureClient:
        return self

    def __exit__(self, *_: Any) -> None:
        if self._owns_client:
            self._client.close()

    def _authenticate(self) -> dict[str, str]:
        if self.config.get("m2m_client_id") and time.time() >= self._capture_refresh_at:
            self._headers.pop(AUTHORIZATION_HEADER, None)
        if self._diapason_id and time.time() >= self._diapason_refresh_at:
            self._headers.pop(DIAPASON_API_JWT_HEADER, None)
        if AUTHORIZATION_HEADER not in self._headers:
            if self.config.get("m2m_client_id"):
                token_url = str(self.config.get("m2m_token_url") or "").strip()
                if not token_url:
                    try:
                        token_url = m2m_token_url_from_registry(_required(self.config, "registry_url"), client=self._client)
                    except RegistryError:
                        raise _AuthenticationError("Failed to resolve M2M token URL from registry") from None
                body = _auth_json(self._client.post(
                    token_url, auth=httpx.BasicAuth(_required(self.config, "m2m_client_id"), _required(self.config, "m2m_client_secret")),
                    data={"grant_type": "client_credentials"}, headers={"Accept": "application/json"},
                ), "M2M token")
                token = str(body.get("access_token") or "").strip()
                if not token:
                    raise _AuthenticationError("M2M token: missing access_token")
                self._capture_refresh_at = _refresh_at(token, body.get("expires_in"))
            else:
                token = _required(self.config, "capture_jwt_token")
            self._headers[AUTHORIZATION_HEADER] = "Bearer " + token
        if DIAPASON_API_JWT_HEADER not in self._headers:
            if self._diapason_id:
                response = self._client.post(self._headers[DIAPASON_BASE_URL_HEADER] + "/api/login", data={
                    "client_id": self._diapason_id, "client_secret": self._diapason_secret, "locale": "en_US",
                })
                if response.status_code != 200:
                    raise _AuthenticationError(f"Diapason login: HTTP {response.status_code}")
                try:
                    root = ET.fromstring(response.content)
                except ET.ParseError:
                    raise _AuthenticationError("Diapason login: expected XML") from None
                token = (root.get("apiToken") or root.get("token") or "").strip()
                if not token:
                    raise _AuthenticationError("Diapason login: missing apiToken")
                self._diapason_refresh_at = _refresh_at(token)
            else:
                token = _required(self.config, "diapason_api_jwt_token")
            self._headers[DIAPASON_API_JWT_HEADER] = token
        return dict(self._headers)

    def metadata(self) -> dict:
        """Best-effort read-only build/catalog identity; never return auth/config."""
        result: dict[str, Any] = {}
        try:
            response = self._client.get(self.url + "/health")
            if response.status_code != 200:
                response = self._client.get(self.url + "/api/health")
            body = _auth_json(response, "Health")
            result["build"] = {key: body[key] for key in ("status", "revision", "release", "build_date")
                               if isinstance(body.get(key), (str, int, float, bool))}
        except (httpx.HTTPError, ValueError):
            result["build_error"] = "unavailable"
        try:
            headers = self._authenticate()
            body = _auth_json(self._client.get(self.url + "/api/capture", headers={AUTHORIZATION_HEADER: headers[AUTHORIZATION_HEADER]}), "Catalog")
            result["catalog"] = {key: body[key] for key in ("enabled", "prompt_version")
                                 if isinstance(body.get(key), (str, bool))}
            if isinstance(body.get("trade_types"), list):
                result["catalog"]["trade_types"] = [item for item in body["trade_types"] if isinstance(item, str)]
        except (httpx.HTTPError, ValueError):
            result["catalog_error"] = "unavailable"
        return result

    def capture(self, pdf: Path, trade_type: str, output_dir: Path, *, correlation_id: str | None = None) -> dict:
        """Capture once with debug data. Failures remain exportable and gradeable."""
        pdf, output_dir = Path(pdf), Path(output_dir)
        if not isinstance(trade_type, str) or not trade_type.strip():
            raise ApiConfigError("Trade type must be nonempty")
        if output_dir.exists():
            raise ApiConfigError("Output directory already exists; choose a fresh path")
        try:
            pdf_bytes = pdf.read_bytes()
        except OSError:
            raise ApiConfigError("Cannot read input PDF") from None
        correlation_id = correlation_id or "capture-eval-" + uuid.uuid4().hex
        if not isinstance(correlation_id, str) or not correlation_id.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in correlation_id):
            raise ApiConfigError("Correlation ID must contain printable ASCII characters")
        try:
            output_dir.mkdir(parents=True, exist_ok=False)
        except OSError:
            raise ApiConfigError("Cannot create fresh output directory") from None
        started = time.perf_counter()
        result: dict[str, Any] = {
            "schema_version": 1, "started_at": datetime.now(timezone.utc).isoformat(),
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(), "trade_type": trade_type.strip(),
            "correlation_id": correlation_id, "status_code": None, "success": False,
            "error": None, "error_category": None, "artifacts": {},
        }
        body = None
        try:
            headers = self._authenticate()
            headers[CORRELATION_HEADER] = correlation_id
            response = self._client.post(
                self.url + "/api/capture", headers=headers,
                data={"trade_type": trade_type.strip(), "debug": "true"},
                files={"pdf": (pdf.name, pdf_bytes, "application/pdf")}, timeout=self.timeout,
            )
            result["status_code"] = response.status_code
            if response.status_code == 401:
                # Preserve this failed attempt; only refresh on the next explicit call.
                if self.config.get("m2m_client_id"):
                    self._headers.pop(AUTHORIZATION_HEADER, None)
                if self._diapason_id:
                    self._headers.pop(DIAPASON_API_JWT_HEADER, None)
            result.update(save_response(response, output_dir))
            try:
                decoded = response.json()
                body = decoded if isinstance(decoded, dict) else None
            except ValueError:
                body = None
            if not 200 <= response.status_code < 300:
                result.update(error=f"Capture API: HTTP {response.status_code}", error_category="http")
            elif body is None:
                result.update(error="Capture API: expected a JSON object", error_category="protocol")
            elif body.get("success") is not True:
                result.update(error="Capture API reported an unsuccessful result", error_category="business")
            elif not isinstance(body.get("trade_xml"), str) or not body["trade_xml"].strip():
                result.update(error="Capture API: missing resolved XML", error_category="protocol")
            else:
                try:
                    ET.fromstring(body["trade_xml"])
                    result["success"] = True
                except ET.ParseError:
                    result.update(error="Capture API: invalid resolved XML", error_category="protocol")
        except _AuthenticationError as exc:
            result.update(error=str(exc), error_category="authentication")
        except (httpx.HTTPError, httpx.InvalidURL):
            result.update(error="HTTP request failed; check connectivity and service logs", error_category="transport")
        except OSError:
            raise ApiConfigError("Cannot write capture artifacts") from None
        finally:
            result["duration_seconds"] = round(time.perf_counter() - started, 6)
            try:
                (output_dir / "run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except OSError:
                raise ApiConfigError("Cannot write capture run metadata") from None
        return {**result, "response": body}
