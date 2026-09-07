"""Health, locale, prompt refresh, catalogue, and legacy token administration."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from pascal import build_info
from pascal.i18n import DEFAULT_LOCALE, locale_from_header_value, strings_for_locale
from pascal.security.jwt import TokenValidationError


class MintTokenBody(BaseModel):
    sub: str
    roles: list[str] = Field(min_length=1)
    customer_id: int | None = None
    ttl_days: int | None = None
    ttl_seconds: int | None = None


class RevokeTokenBody(BaseModel):
    jti: str | None = None
    sub: str | None = None
    reason: str = ""


def router(deps: dict) -> APIRouter:
    api = APIRouter()
    optional_bearer = HTTPBearer(auto_error=False)

    @api.get("/health", include_in_schema=False)
    async def health():
        return build_info.health()

    @api.get("/ready", include_in_schema=False)
    async def ready(request: Request):
        if not getattr(request.app.state, "ready", False) or request.app.state.chat.closing:
            raise HTTPException(503, "Not ready")
        return {"status": "ok"}

    @api.get("/api/i18n")
    async def i18n(request: Request):
        locale = locale_from_header_value(
            request.query_params.get("locale") or request.headers.get("X-Diapason-Locale")
        )
        return {
            "locale": locale,
            "default_locale": DEFAULT_LOCALE,
            "strings": strings_for_locale(locale),
        }

    @api.get("/api/health")
    async def api_health(request: Request, credentials=Depends(optional_bearer)):
        state = request.app.state
        info = build_info.load()
        payload = dict(
            status="ok",
            chat_version=info["version"],
            revision=info["revision"],
            assistant_name=state.config.get("ui", {}).get("assistant_name", "Pascal"),
            assistant_identity_configured=bool(
                state.config.get("ui", {}).get("assistant_identity")
            ),
            locale=locale_from_header_value(request.headers.get("X-Diapason-Locale")),
            default_locale=DEFAULT_LOCALE,
            sessions_backend=state.store.backend,
            prompt_source=state.prompts.snapshot.source,
            prompt_length=len(state.prompts.snapshot.text),
            intelligence_contract_enabled=bool(state.config.get("capture", {}).get("enabled")),
        )
        if credentials:
            try:
                claims = state.auth.validate(credentials.credentials)
                payload["jwt"] = {
                    key: claims[key]
                    for key in (
                        "iss",
                        "sub",
                        "roles",
                        "jti",
                        "exp",
                        "customer_id",
                    )
                    if key in claims
                }
            except TokenValidationError as exc:
                payload["jwt"] = {"valid": False, "error": str(exc)}
        return payload

    @api.get("/api/mcp/tools")
    async def tools(request: Request, identity=Depends(deps["get_identity"])):
        async with asyncio.timeout(request.app.state.chat.limits.turn_timeout_seconds):
            result = await request.app.state.registry.discover(identity.mcp, identity.scope_path)
        return result.public()

    @api.post("/api/refresh-prompt")
    async def refresh(request: Request, _claims=Depends(deps["require_refresh"])):
        try:
            return await asyncio.to_thread(request.app.state.prompts.refresh)
        except Exception as exc:
            raise HTTPException(502, "Prompt refresh failed; previous prompt retained") from exc

    @api.post("/api/auth/tokens")
    async def mint(body: MintTokenBody, request: Request, _claims=Depends(deps["require_admin"])):
        return await asyncio.to_thread(request.app.state.auth.mint, **body.model_dump())

    @api.post("/api/auth/revoke")
    async def revoke(
        body: RevokeTokenBody, request: Request, _claims=Depends(deps["require_admin"])
    ):
        if not body.jti and not body.sub:
            raise HTTPException(400, "jti or sub required")
        await asyncio.to_thread(request.app.state.auth.revoke, jti=body.jti, sub=body.sub)
        return {"ok": "true"}

    return api
