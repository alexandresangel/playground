"""Stateless extraction HTTP contract."""

from __future__ import annotations

from contextlib import nullcontext
from opentelemetry.trace import Status, StatusCode
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.responses import Response
from typing import Any, Dict, Optional

from auth_m2m import Identity
from capture.observability.http import apply_identity_span_attrs, record_capture_result
from capture.http_contract import CORRELATION_HEADER
from capture.workflow.prompts import capture_enabled, capture_prompt_version, capture_trade_types
from capture.runtime import Runtime
from capture.workflow.graph import run_capture


def _capture_public_response(result: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(result)
    out.pop("timings_ms", None)
    out.pop("tool_trace", None)
    return out


def create_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()
    get_identity = runtime.get_identity
    require_capture = runtime.require_capture

    @router.get("/api/skills/intelligence-contract", deprecated=True)
    @router.get("/api/capture")
    def capture_metadata(
        _claims: dict = Depends(require_capture),
    ) -> Dict[str, Any]:
        if not capture_enabled(runtime.config):
            raise HTTPException(status_code=404, detail="Capture is disabled")
        return {
            "enabled": True,
            "trade_types": capture_trade_types(),
            "prompt_version": capture_prompt_version(),
        }

    @router.post("/api/skills/intelligence-contract", deprecated=True)
    @router.post("/api/capture")
    async def capture_extract(
        request: Request,
        identity: Identity = Depends(get_identity),
        pdf: UploadFile = File(...),
        trade_type: str = Form(...),
        debug: str = Form("false"),
        session_id: Optional[str] = Form(None),
    ) -> Response:
        if not capture_enabled(runtime.config):
            raise HTTPException(status_code=404, detail="Capture is disabled")
        azure = runtime.azure_client()
        if not azure:
            raise HTTPException(status_code=503, detail="Azure OpenAI is not configured")
        try:
            session_header = request.headers.get(CORRELATION_HEADER)
            # Correlation only: no session lookup, creation, or persistence.
            session_id = (session_id or "").strip() or (
                session_header.strip() if isinstance(session_header, str) and session_header.strip() else None
            ) or request.state.correlation_id
            request.state.correlation_id = session_id
            span_cm = (
                runtime.tracer.start_as_current_span(
                    "capture.request", record_exception=False, set_status_on_exception=False
                ) if runtime.tracer else nullcontext()
            )
            with span_cm as span:
                apply_identity_span_attrs(
                    runtime, span, customer_id=identity.customer_id, user_id=identity.user_id,
                    session_id=session_id, scope=identity.scope_path,
                )
                pdf_bytes = await pdf.read()
                trade_type = trade_type.strip()
                debug_mode = debug.strip().lower() in ("1", "true", "yes", "on")
                try:
                    result = await run_capture(
                        pdf_bytes=pdf_bytes, trade_type=trade_type, cluster=identity.mcp,
                        config=runtime.config, azure=azure, debug=debug_mode,
                    )
                except (ValueError, RuntimeError) as exc:
                    if span is not None:
                        span.set_status(Status(StatusCode.ERROR))
                        span.set_attribute("error.type", type(exc).__name__)
                    code = 400 if isinstance(exc, ValueError) else 502
                    raise HTTPException(status_code=code, detail=str(exc)) from exc
                except Exception as exc:
                    if span is not None:
                        span.set_status(Status(StatusCode.ERROR))
                        span.set_attribute("error.type", type(exc).__name__)
                    raise
                record_capture_result(runtime, span, identity=identity, session_id=session_id, result=result)

            return JSONResponse(
                content=_capture_public_response(result),
                headers={CORRELATION_HEADER: session_id},
            )
        finally:
            azure["client"].close()

    return router
