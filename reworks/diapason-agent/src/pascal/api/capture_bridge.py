"""Keep the existing composer route; all extraction belongs to the Capture service."""

import asyncio

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from opentelemetry.propagate import inject

from pascal.agent.service import BusyError
from pascal.agent.state import ExternalFailure, ExternalResult
from pascal.api.chat import SESSION_HEADER
from pascal.compatibility import CAPTURE_HTTP_PATH
from pascal.i18n import locale_from_header_value, translate

PATH = CAPTURE_HTTP_PATH
FORWARD_HEADERS = (
    "Authorization",
    "X-Diapason-User-Id",
    "X-Diapason-Customer-Id",
    "X-Diapason-Mcp-Token",
    "X-Diapason-Mcp-Scope",
    "X-Diapason-Mcp-Base-Url",
    "X-Diapason-Locale",
    SESSION_HEADER,
)


def router(deps: dict) -> APIRouter:
    api = APIRouter()

    async def forward(request, method, **kwargs):
        config = request.app.state.config.get("capture", {})
        if not config.get("enabled"):
            raise HTTPException(404, "Capture is disabled")
        endpoint = str(config.get("base_url", "")).rstrip("/")
        if not endpoint:
            raise HTTPException(503, "Capture endpoint is not configured")
        headers = {
            name: request.headers[name] for name in FORWARD_HEADERS if name in request.headers
        }
        inject(headers)
        outgoing = httpx.Request(
            method,
            endpoint + PATH,
            headers=headers,
            **kwargs,
            extensions={"timeout": httpx.Timeout(float(config.get("timeout_s", 210))).as_dict()},
        )
        try:
            response = await request.app.state.capture_client.send(outgoing)
            if response.status_code >= 300:
                raise HTTPException(
                    response.status_code if response.status_code < 500 else 502,
                    "Capture request failed",
                )
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Invalid capture response")
            return result
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, "Capture unavailable") from exc

    @api.get(PATH)
    async def metadata(request: Request, _claims=Depends(deps["require_chat"])):
        return await forward(request, "GET")

    @api.post(PATH)
    async def capture(
        request: Request,
        identity=Depends(deps["get_identity"]),
        pdf: UploadFile = File(...),
        trade_type: str = Form(...),
        debug: str = Form("false"),
        session_id: str | None = Form(None),
    ):
        config = request.app.state.config.get("capture", {})
        if not config.get("enabled"):
            raise HTTPException(404, "Capture is disabled")
        limit = int(config.get("max_pdf_bytes", 10485760))
        content = await pdf.read(limit + 1)
        if len(content) > limit:
            raise HTTPException(413, "PDF is too large")
        locale = locale_from_header_value(request.headers.get("X-Diapason-Locale"))

        async def execute(sid):
            try:
                result = await forward(
                    request,
                    "POST",
                    data={
                        "trade_type": trade_type,
                        "debug": debug,
                        "session_id": sid,
                    },
                    files={"pdf": (pdf.filename or "contract.pdf", content, "application/pdf")},
                )
            except HTTPException as exc:
                raise ExternalFailure(exc.status_code) from exc
            label = translate(f"ic.tradeType.{trade_type}", locale)
            if label.startswith("ic.tradeType."):
                label = trade_type
            answer = (
                translate(
                    "ic.successOutcome",
                    locale,
                    {
                        "tradeTypeLabel": label,
                        "fieldCount": result.get("extracted_field_count", 0),
                    },
                )
                if result.get("success")
                else str(result.get("message") or translate("ic.error", locale))
            )
            result.pop("session_artifacts", None)
            result.pop("timings_ms", None)
            # The public XML remains only in the HTTP result, never in the transcript.
            return ExternalResult(
                result,
                answer,
                {
                    "operation": "capture",
                    "trade_type": trade_type,
                    "success": bool(result.get("success")),
                },
            )

        filename = pdf.filename or "contract.pdf"
        try:
            handle = await request.app.state.chat.open(
                identity=identity,
                session_id=session_id or request.headers.get(SESSION_HEADER),
                message=f"Capture import {trade_type} from {filename}",
                locale=locale,
                external=execute,
            )
        except KeyError as exc:
            raise HTTPException(404, "Unknown session_id") from exc
        except BusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, "Invalid Capture request") from exc
        except Exception as exc:
            raise HTTPException(503, "Capture preparation unavailable") from exc
        try:
            await asyncio.shield(handle.task)
        except asyncio.CancelledError:
            await handle.disconnect()
            raise
        if not handle.outcome.persisted:
            raise HTTPException(503, "Capture receipt could not be saved")
        if handle.outcome.public_result is None:
            raise HTTPException(handle.outcome.error_status, "Capture could not complete")
        return JSONResponse(
            handle.outcome.public_result, headers={SESSION_HEADER: handle.session_id}
        )

    return api
