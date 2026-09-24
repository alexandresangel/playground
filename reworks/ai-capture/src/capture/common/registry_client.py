"""Load platform registry/services.json and resolve service URLs."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

REGISTRY_HTTP_TIMEOUT_SECONDS = 5.0


class RegistryError(Exception):
    pass


def registry_url_from_config(config: Dict[str, Any]) -> str:
    """Mandatory ``registry_url`` from CAPTURE_CONFIG / config JSON only (no env)."""
    raw = config.get("registry_url")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    raise RegistryError(
        "Missing config.registry_url (required in CAPTURE_CONFIG / config JSON)."
    )


def fetch_services(registry_url: str, *, client: Optional[httpx.Client] = None) -> Dict[str, Any]:
    """GET services.json; return the ``services`` object (keyed by logical name)."""
    url = (registry_url or "").strip()
    if not url:
        raise RegistryError("registry URL is empty")
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise RegistryError("registry URL must be absolute http(s)")
    owns = client is None
    http = client or httpx.Client(timeout=REGISTRY_HTTP_TIMEOUT_SECONDS, follow_redirects=False)
    try:
        resp = http.get(url)
        if resp.status_code != 200:
            raise RegistryError(f"registry fetch failed: HTTP {resp.status_code}")
        if urlparse(str(resp.url)).netloc != parsed.netloc:
            raise RegistryError("registry redirect to unexpected host")
        try:
            body = resp.json()
        except ValueError as exc:
            raise RegistryError("registry response is not JSON") from exc
        services = body.get("services") if isinstance(body, dict) else None
        if not isinstance(services, dict) or not services:
            raise RegistryError("registry has no services")
        return services
    finally:
        if owns:
            http.close()


def service_url(services: Dict[str, Any], key: str) -> str:
    entry = services.get(key)
    if not isinstance(entry, dict):
        raise RegistryError(f"registry missing service '{key}'")
    url = entry.get("url")
    if not isinstance(url, str) or not url.strip():
        raise RegistryError(f"registry service '{key}' has no url")
    return url.strip()


def m2m_token_url_from_registry(
    registry_url: str,
    *,
    client: Optional[httpx.Client] = None,
) -> str:
    """Return registry ``services.m2m.url`` (token endpoint)."""
    services = fetch_services(registry_url, client=client)
    return service_url(services, "m2m")