"""Operational endpoints for Capture, independent of Pascal's system prompt."""

from capture.workflow.prompts import capture_enabled, refresh_capture_prompts
from capture.runtime import Runtime
from fastapi import APIRouter, Depends, HTTPException
import build_info


def create_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()
    require_refresh = runtime.require_refresh

    @router.get("/health", include_in_schema=False)
    def deploy_health() -> dict:
        return build_info.health()

    @router.get("/api/health")
    def health() -> dict:
        return build_info.health()

    @router.post("/api/refresh-prompt")
    def refresh_prompt(_refresh: dict = Depends(require_refresh)) -> dict:
        if not capture_enabled(runtime.config):
            raise HTTPException(status_code=404, detail="Intelligence contract skill is disabled")
        try:
            return refresh_capture_prompts(runtime.config)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return router
