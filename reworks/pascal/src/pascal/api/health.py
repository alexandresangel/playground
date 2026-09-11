from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Any, Dict, Optional
import logging

from dia_jwt import TokenValidationError
from dia_jwt.fastapi import Identity
import build_info
from i18n import DEFAULT_LOCALE, LOCALE_HEADER, normalize_locale, strings_for_locale
from prompt_loader import get_system_prompt, prompt_source, refresh_system_prompt
from settings import assistant_identity, assistant_name
from pascal.integrations.capture import capture_enabled, public_response, request_capture
from pascal.agent.discovery import _list_mcp_tools
from pascal.api.schemas import McpToolsListResponse
from pascal.observability.routing import quiet_access
from pascal.runtime import Runtime, locale_from_request

log = logging.getLogger("diapason.chat")


def create_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()
    get_identity = runtime.get_identity
    require_refresh = runtime.require_refresh
    _optional_bearer = HTTPBearer(auto_error=False)

    @router.get("/api/i18n")
    @quiet_access
    def get_i18n(request: Request) -> Dict[str, Any]:
        """UI strings for the active locale (from X-Diapason-Locale or ?locale=)."""
        query_locale = request.query_params.get("locale")
        loc = normalize_locale(query_locale or request.headers.get(LOCALE_HEADER))
        return {
            "locale": loc,
            "default_locale": DEFAULT_LOCALE,
            "strings": strings_for_locale(loc),
        }

    @router.get("/health", include_in_schema=False)
    @quiet_access
    def deploy_health() -> Dict[str, str]:
        return build_info.health()

    @router.get("/api/health")
    @quiet_access
    def health(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    ) -> Dict[str, Any]:
        info = build_info.load()
        payload: Dict[str, Any] = {
            "status": "ok",
            "chat_version": info["version"],
            "revision": info["revision"],
            "assistant_name": assistant_name(runtime.config),
            "assistant_identity_configured": bool(assistant_identity(runtime.config)),
            "locale": locale_from_request(request),
            "default_locale": DEFAULT_LOCALE,
            "sessions_backend": getattr(runtime.sessions, "backend", "unknown"),
            "prompt_source": prompt_source(),
            "prompt_length": len(get_system_prompt()),
            "intelligence_contract_enabled": capture_enabled(runtime.config),
        }
        if credentials and credentials.credentials:
            try:
                claims = runtime.auth.validate(credentials.credentials)
                payload["jwt"] = {
                    k: claims.get(k)
                    for k in ("iss", "sub", "roles", "jti", "exp", "customer_id")
                    if k in claims
                }
            except TokenValidationError as exc:
                payload["jwt"] = {"valid": False, "error": str(exc)}
        return payload

    @router.post("/api/refresh-prompt", response_model=Dict[str, Any])
    async def refresh_prompt(request: Request, _refresh: dict = Depends(require_refresh)):
        try:
            out = refresh_system_prompt(runtime.config, runtime.base_dir)
            if capture_enabled(runtime.config):
                upstream = await request_capture(request, "/api/refresh-prompt", method="POST")
                if not upstream.is_success:
                    return public_response(upstream)
                out["intelligence_contract"] = upstream.json()
            return out
        except HTTPException:
            raise
        except Exception as exc:
            log.exception("POST /api/refresh-prompt failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.get("/api/mcp/tools", response_model=McpToolsListResponse)
    def list_mcp_tools_endpoint(
        identity: Identity = Depends(get_identity),
    ) -> McpToolsListResponse:
        """List tools from all configured MCP servers (same merge as chat tool-calling)."""
        return _list_mcp_tools(runtime, identity.mcp, for_chat_api=True)

    @router.get("/")
    def index() -> FileResponse:
        return FileResponse((runtime.base_dir / "static") / "index.html")

    return router
