"""Classic HTTP contract; business execution belongs to CaptureRuntime."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from capture import build_info
from capture.auth import CaptureIdentity
from capture.compatibility import CHAT_SESSION_HEADER, LEGACY_CAPTURE_PATH, public_result


def create_router(capture_runtime, capture_security) -> APIRouter:
    api = APIRouter()
    bearer = HTTPBearer(auto_error=True)

    def require_capture(
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    ) -> dict[str, Any]:
        return capture_security.claims_from_credentials(credentials)

    def get_identity(
        request: Request,
        claims: Annotated[dict[str, Any], Depends(require_capture)],
    ) -> CaptureIdentity:
        return capture_security.identity_from_headers(request.headers, claims)

    @api.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return build_info.health()

    @api.get("/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        is_ready = (not capture_runtime.enabled) or capture_runtime.catalog.ready
        status = 200 if is_ready else 503
        return JSONResponse(
            status_code=status,
            content={"status": "ready" if is_ready else "not_ready", "service": "capture"},
        )

    @api.get(LEGACY_CAPTURE_PATH)
    async def capture_metadata(
        _claims: Annotated[dict[str, Any], Depends(require_capture)],
    ) -> dict[str, Any]:
        if not capture_runtime.enabled:
            raise HTTPException(status_code=404, detail="Capture is disabled")
        return capture_runtime.catalog.metadata()

    @api.post(LEGACY_CAPTURE_PATH)
    async def capture_contract(
        request: Request,
        identity: Annotated[CaptureIdentity, Depends(get_identity)],
        pdf: Annotated[UploadFile, File()],
        trade_type: Annotated[str, Form()],
        debug: Annotated[str, Form()] = "false",
        session_id: Annotated[str | None, Form()] = None,
    ) -> JSONResponse:
        if not capture_runtime.enabled:
            raise HTTPException(status_code=404, detail="Capture is disabled")
        pdf_bytes = await pdf.read(capture_runtime.max_pdf_bytes + 1)
        try:
            result = await capture_runtime.execute(
                pdf_bytes=pdf_bytes,
                trade_type=trade_type.strip(),
                identity=identity,
                debug=debug.strip().lower() in {"1", "true", "yes", "on"},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Capture could not complete") from exc

        response_headers: dict[str, str] = {}
        resolved_session = (session_id or request.headers.get(CHAT_SESSION_HEADER) or "").strip()
        if resolved_session:
            response_headers[CHAT_SESSION_HEADER] = resolved_session
        return JSONResponse(content=public_result(result), headers=response_headers)

    return api
