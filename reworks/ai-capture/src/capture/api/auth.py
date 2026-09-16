"""api: auth: company HTTP behavior with explicit runtime dependencies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict

from capture.api.schemas import MintTokenBody, RevokeTokenBody
from capture.runtime import Runtime


def create_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()
    require_admin = runtime.require_admin

    @router.post("/api/auth/tokens")
    def mint_instance_token(
        body: MintTokenBody,
        _admin: dict = Depends(require_admin),
    ) -> Dict[str, Any]:
        return runtime.auth.mint(
            sub=body.sub,
            roles=body.roles,
            customer_id=body.customer_id,
            ttl_days=body.ttl_days,
            ttl_seconds=body.ttl_seconds,
        )

    @router.post("/api/auth/revoke")
    def revoke_token(
        body: RevokeTokenBody,
        _admin: dict = Depends(require_admin),
    ) -> Dict[str, str]:
        if not body.jti and not body.sub:
            raise HTTPException(status_code=400, detail="jti or sub required")
        runtime.auth.revoke(jti=body.jti, sub=body.sub)
        return {"ok": "true"}

    return router