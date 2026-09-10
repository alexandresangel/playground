"""Preserve Pascal upload execution while the separate Capture service is connected."""

from __future__ import annotations
from pascal.compat.capture.prompts import capture_enabled, capture_prompt_version, capture_trade_types
from pascal.compat.capture.graph import run_capture
from contextlib import nullcontext
from dia_jwt.fastapi import Identity
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from i18n import strings_for_locale, translate
from pascal.observability.http import _emit_chat_observability
from pascal.runtime import Runtime, _resolve_session_id, _session_store_error, locale_from_request
from starlette.responses import Response
from typing import Any, Dict, Optional

CHAT_SESSION_HEADER = "X-Diapason-Chat-Session"


def _ic_user_message(trade_type: str, pdf_filename: str) -> str:
    return f"@intelligence-contract import {trade_type.strip()} from {pdf_filename.strip() or 'contract.pdf'}"


def _ic_trade_type_label(trade_type: str, locale: str) -> str:
    key = (trade_type or "").strip()
    if not key:
        return ""
    label_key = f"ic.tradeType.{key}"
    label = translate(label_key, locale)
    return key if label == label_key else label


def _ic_success_message(result: Dict[str, Any], locale: str) -> str:
    trade_type = str(result.get("trade_type") or "")
    count = result.get("extracted_field_count")
    try:
        field_count = int(count) if count is not None else 0
    except (TypeError, ValueError):
        field_count = 0
    return translate(
        "ic.successOutcome",
        locale,
        {
            "tradeTypeLabel": _ic_trade_type_label(trade_type, locale),
            "fieldCount": field_count,
        },
    )


def _ic_assistant_message(result: Dict[str, Any], locale: str) -> str:
    s = strings_for_locale(locale)
    if result.get("success"):
        return _ic_success_message(result, locale).strip() or "Intelligence contract completed."
    msg = f'{s.get("ic.error", "Error")}: {result.get("message") or s.get("response.none", "")}'
    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        label = s.get("ic.warnings", "Warnings")
        msg += "\n\n" + label + ":\n" + "\n".join(f"- {w}" for w in warnings if w)
    return msg


def _ic_public_response(result: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(result)
    out.pop("session_artifacts", None)
    out.pop("timings_ms", None)
    return out


def create_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()
    get_identity = runtime.get_identity
    require_chat = runtime.require_chat

    @router.get("/api/skills/intelligence-contract")
    def intelligence_contract_metadata(
        _claims: dict = Depends(require_chat),
    ) -> Dict[str, Any]:
        if not capture_enabled(runtime.config):
            raise HTTPException(status_code=404, detail="Intelligence contract skill is disabled")
        return {
            "enabled": True,
            "trade_types": capture_trade_types(),
            "prompt_version": capture_prompt_version(),
        }

    @router.post("/api/skills/intelligence-contract")
    async def intelligence_contract_skill(
        request: Request,
        identity: Identity = Depends(get_identity),
        pdf: UploadFile = File(...),
        trade_type: str = Form(...),
        debug: str = Form("false"),
        session_id: Optional[str] = Form(None),
    ) -> Response:
        if not capture_enabled(runtime.config):
            raise HTTPException(status_code=404, detail="Intelligence contract skill is disabled")
        azure = runtime.azure_client()
        if not azure:
            raise HTTPException(status_code=503, detail="Azure OpenAI is not configured")
        try:
            loc = locale_from_request(request)
            session_header = request.headers.get(CHAT_SESSION_HEADER)
            resolved_session = (session_id or "").strip() or (
                session_header.strip() if isinstance(session_header, str) and session_header.strip() else None
            )
            try:
                session_id = _resolve_session_id(runtime, identity.scope_path, resolved_session)
            except HTTPException:
                raise
            pdf_bytes = await pdf.read()
            pdf_filename = (pdf.filename or "").strip() or "contract.pdf"
            trade_type = trade_type.strip()
            debug_mode = debug.strip().lower() in ("1", "true", "yes", "on")
            try:
                result = await run_capture(
                    pdf_bytes=pdf_bytes,
                    trade_type=trade_type,
                    cluster=identity.mcp,
                    config=runtime.config,
                    azure=azure,
                    debug=debug_mode,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

            skill_run = {
                "skill": "intelligence-contract",
                "trade_type": result.get("trade_type"),
                "view_entity": result.get("view_entity"),
                "menu_name": result.get("menu_name"),
                "pdf_filename": pdf_filename,
                "success": bool(result.get("success")),
                "warnings": result.get("warnings") if isinstance(result.get("warnings"), list) else [],
                "artifacts": result.get("session_artifacts") if isinstance(result.get("session_artifacts"), dict) else {},
                "timings_ms": result.get("timings_ms") if isinstance(result.get("timings_ms"), dict) else {},
            }
            user_msg = _ic_user_message(trade_type, pdf_filename)
            assistant_msg = _ic_assistant_message(result, loc)
            tool_trace = result.get("tool_trace") if isinstance(result.get("tool_trace"), list) else None
            span_cm = (
                runtime.tracer.start_as_current_span("chat.completion", record_exception=False, set_status_on_exception=False)
                if runtime.tracer
                else nullcontext()
            )
            with span_cm as span:
                try:
                    runtime.sessions.append_turn(
                        session_id,
                        identity.scope_path,
                        user_msg,
                        assistant_msg,
                        tool_trace=tool_trace,
                        skill_run=skill_run,
                    )
                except RuntimeError as exc:
                    raise _session_store_error(exc) from exc
                _emit_chat_observability(runtime, 
                    span,
                    identity=identity,
                    session_id=session_id,
                    user_message=user_msg,
                    tool_trace=tool_trace if isinstance(tool_trace, list) else None,
                    skill_run=skill_run,
                )

            return JSONResponse(
                content=_ic_public_response(result),
                headers={CHAT_SESSION_HEADER: session_id},
            )
        finally:
            azure["client"].close()

    return router
