"""Keep Pascal's existing UI endpoints while Capture owns execution and persistence."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from starlette.responses import Response

from dia_jwt.fastapi import Identity
from pascal.integrations.capture import (
    EXTRACTION_PATH, capture_enabled, public_response, request_capture,
)
from pascal.runtime import Runtime


def create_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()

    def check_enabled() -> None:
        if not capture_enabled(runtime.config):
            raise HTTPException(status_code=404, detail="Intelligence contract skill is disabled")

    @router.get(EXTRACTION_PATH, response_model=Dict[str, Any])
    async def intelligence_contract_metadata(
        request: Request, _claims: dict = Depends(runtime.require_chat),
    ) -> Response:
        check_enabled()
        return public_response(await request_capture(request, EXTRACTION_PATH))

    @router.post(EXTRACTION_PATH)
    async def intelligence_contract_skill(
        request: Request,
        identity: Identity = Depends(runtime.get_identity),
        pdf: UploadFile = File(...),
        trade_type: str = Form(...),
        debug: str = Form("false"),
        session_id: Optional[str] = Form(None),
    ) -> Response:
        check_enabled()
        data = {"trade_type": trade_type, "debug": debug}
        if session_id is not None:
            data["session_id"] = session_id
        upstream = await request_capture(
            request, EXTRACTION_PATH, method="POST", data=data,
            files={"pdf": (pdf.filename or "contract.pdf", await pdf.read(), pdf.content_type or "application/pdf")},
        )
        return public_response(upstream)

    return router
