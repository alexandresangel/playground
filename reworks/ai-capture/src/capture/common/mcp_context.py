"""MCP servers from config: mcp.default (Diapason + config_key) and named extras (headers)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Collection, Dict, List, Optional, Tuple

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request

from settings import load_config

log = logging.getLogger("diapason.chat.mcp")

PRIMARY_SERVER_ID = "default"
DIAPASON_SERVER_ID = PRIMARY_SERVER_ID

DIAPASON_API_JWT_HEADER = "X-Diapason-Mcp-Token"
DIAPASON_SCOPE_HEADER = "X-Diapason-Mcp-Scope"
DIAPASON_BASE_URL_HEADER = "X-Diapason-Mcp-Base-Url"
MCP_VERSION_HEADER = "X-Diapason-Mcp-Protocol-Version"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"

_SERVER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


@dataclass(frozen=True)
class McpServerContext:
    server_id: str
    label: str
    server_url: str
    request_headers: Dict[str, str] = field(default_factory=dict)
    protocol_version: str = DEFAULT_PROTOCOL_VERSION


@dataclass(frozen=True)
class McpCluster:
    servers: Tuple[McpServerContext, ...]

    @property
    def primary(self) -> McpServerContext:
        return self.servers[0]

    @property
    def diapason(self) -> McpServerContext:
        return self.primary

    def server_ids(self) -> Tuple[str, ...]:
        return tuple(s.server_id for s in self.servers)

    def get(self, server_id: str) -> Optional[McpServerContext]:
        sid = _normalize_server_id(server_id)
        for server in self.servers:
            if server.server_id == sid:
                return server
        return None


McpContext = McpServerContext


def _normalize_server_id(server_id: str) -> str:
    sid = (server_id or "").strip().lower()
    return PRIMARY_SERVER_ID if sid == "diapason" else sid


def qualify_tool_name(server_id: str, tool_name: str) -> str:
    if _normalize_server_id(server_id) == PRIMARY_SERVER_ID:
        return tool_name
    return f"{_normalize_server_id(server_id)}__{tool_name}"


def parse_qualified_tool_name(qualified: str, server_ids: Collection[str]) -> Tuple[str, str]:
    normalized_ids = {_normalize_server_id(s) for s in server_ids}
    extra_ids = [sid for sid in normalized_ids if sid != PRIMARY_SERVER_ID]
    for sid in sorted(extra_ids, key=len, reverse=True):
        prefix = f"{sid}__"
        if qualified.startswith(prefix):
            return sid, qualified[len(prefix) :]
    return PRIMARY_SERVER_ID, qualified


def _parse_request_headers(block: Dict[str, Any]) -> Dict[str, str]:
    raw = block.get("headers")
    if not isinstance(raw, dict):
        return {}
    headers: Dict[str, str] = {}
    for key, value in raw.items():
        if key is None:
            continue
        name = str(key).strip()
        if not name:
            continue
        headers[name] = "" if value is None else str(value).strip()
    return headers


def _encrypt_diapason_bearer(
    config_key: str, *, diapason_base_url: str, api_token: str, scope: int
) -> str:
    base_url = diapason_base_url.strip().rstrip("/")
    if not config_key:
        raise HTTPException(
            status_code=500,
            detail="Missing mcp.default.config_key (Fernet key, same as MCP_CONFIG_KEY).",
        )
    if not base_url:
        raise HTTPException(
            status_code=400,
            detail=f"Missing {DIAPASON_BASE_URL_HEADER} (Diapason base URL from Tomcat or test config)",
        )

    payload = {"base_url": base_url, "scope": scope, "api_token": api_token}
    try:
        token = Fernet(config_key).encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="Invalid mcp.default.config_key (expected Fernet key).") from exc
    return token.decode("utf-8")


def _default_server_from_request(request: Request, block: Dict[str, Any]) -> McpServerContext:
    url = str(block.get("server_url", "") or "").strip().rstrip("/")
    config_key = str(block.get("config_key", "") or "").strip()
    label = str(block.get("label", "") or "").strip() or "Diapason"
    version = (
        str(block.get("protocol_version", "") or "").strip()
        or request.headers.get(MCP_VERSION_HEADER, "").strip()
        or DEFAULT_PROTOCOL_VERSION
    )

    if not url:
        raise HTTPException(status_code=500, detail="Missing mcp.default.server_url in config.")

    diapason_api_jwt = request.headers.get(DIAPASON_API_JWT_HEADER, "").strip()
    diapason_base_url = request.headers.get(DIAPASON_BASE_URL_HEADER, "").strip()
    scope_raw = request.headers.get(DIAPASON_SCOPE_HEADER, "").strip()
    if not diapason_api_jwt:
        raise HTTPException(
            status_code=400,
            detail=f"Missing {DIAPASON_API_JWT_HEADER} (Diapason API JWT from Tomcat or test config)",
        )
    if not scope_raw:
        raise HTTPException(
            status_code=400,
            detail=f"Missing {DIAPASON_SCOPE_HEADER} (Diapason scope from Tomcat or test config)",
        )
    try:
        scope = int(scope_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{DIAPASON_SCOPE_HEADER} must be an integer") from exc

    headers = _parse_request_headers(block)
    headers["Authorization"] = f"Bearer {_encrypt_diapason_bearer(config_key, diapason_base_url=diapason_base_url, api_token=diapason_api_jwt, scope=scope)}"

    return McpServerContext(
        server_id=PRIMARY_SERVER_ID,
        label=label,
        server_url=url,
        request_headers=headers,
        protocol_version=version,
    )


def _extra_server_from_block(server_id: str, block: Dict[str, Any]) -> Optional[McpServerContext]:
    if block.get("enabled") is False:
        return None
    sid = _normalize_server_id(server_id)
    if sid == PRIMARY_SERVER_ID:
        log.warning("Extra MCP entry %r ignored — use mcp.default for Diapason", server_id)
        return None
    if not _SERVER_ID_RE.match(sid):
        log.warning("Skipping MCP server with invalid id %r", server_id)
        return None
    url = str(block.get("server_url", "") or "").strip().rstrip("/")
    if not url:
        log.warning("Skipping MCP server %s: missing server_url", sid)
        return None
    label = str(block.get("label", "") or "").strip() or sid
    version = str(block.get("protocol_version", "") or "").strip() or DEFAULT_PROTOCOL_VERSION
    return McpServerContext(
        server_id=sid,
        label=label,
        server_url=url,
        request_headers=_parse_request_headers(block),
        protocol_version=version,
    )


def mcp_cluster_from_request(request: Request, config: Dict[str, Any] | None = None) -> McpCluster:
    cfg = config or load_config()
    mcp_cfg = cfg.get("mcp")
    if not isinstance(mcp_cfg, dict) or not mcp_cfg:
        raise HTTPException(status_code=500, detail="Missing mcp section in config.")

    default_block = mcp_cfg.get("default")
    if not isinstance(default_block, dict):
        raise HTTPException(status_code=500, detail='Missing mcp.default { "server_url", "config_key", … }.')

    primary = _default_server_from_request(request, default_block)
    extras: List[McpServerContext] = []
    for key, raw in mcp_cfg.items():
        if key == "default" or not isinstance(raw, dict):
            continue
        server = _extra_server_from_block(key, raw)
        if server is not None:
            extras.append(server)

    extras.sort(key=lambda s: s.server_id)
    return McpCluster(servers=(primary, *extras))


def mcp_from_request(request: Request, config: Dict[str, Any] | None = None) -> McpCluster:
    return mcp_cluster_from_request(request, config)
