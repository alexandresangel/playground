"""FastAPI host for the compatibility HTTP route and stateless MCP transport."""

import asyncio
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from capture import build_info
from capture.config import load_config
from capture.constants import CHAT_SESSION_HEADER, LEGACY_CAPTURE_PATH, REQUEST_ID_HEADER
from capture.mcp_server import create_mcp_server
from capture.runtime import CaptureRuntime, public_result
from capture.security import CaptureIdentity, CaptureSecurity, build_security
from capture.telemetry import instrument_app

log = logging.getLogger("capture.api")


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(
    *,
    config: dict[str, Any] | None = None,
    runtime: CaptureRuntime | None = None,
    security: CaptureSecurity | None = None,
    project_root: Path | None = None,
) -> FastAPI:
    configured_root = (os.getenv("CAPTURE_ROOT") or "").strip()
    root = project_root or (Path(configured_root) if configured_root else Path.cwd())
    settings = config or load_config(root)
    capture_runtime = runtime or CaptureRuntime(settings, root)
    capture_security = security or build_security(root, settings)
    mcp = create_mcp_server(capture_runtime, capture_security, settings)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(capture_runtime.initialize)
        async with mcp.session_manager.run():
            yield

    app = FastAPI(
        title="Diapason Capture",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.capture_runtime = capture_runtime
    app.state.capture_security = capture_security

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = (request.headers.get(REQUEST_ID_HEADER) or "").strip()
        if not request_id or len(request_id) > 128:
            request_id = str(uuid.uuid4())
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception(
                "request event=failed method=%s path=%s request_id=%s duration_ms=%d",
                request.method,
                request.url.path,
                request_id,
                int((time.perf_counter() - started) * 1000),
            )
            raise
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path == LEGACY_CAPTURE_PATH or request.url.path.startswith("/mcp"):
            response.headers["Cache-Control"] = "no-store"
        log.info(
            "request event=completed method=%s path=%s status=%d request_id=%s duration_ms=%d",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            int((time.perf_counter() - started) * 1000),
        )
        return response

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

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return build_info.health()

    @app.get("/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        is_ready = (not capture_runtime.enabled) or capture_runtime.catalog.ready
        status = 200 if is_ready else 503
        return JSONResponse(
            status_code=status,
            content={"status": "ready" if is_ready else "not_ready", "service": "capture"},
        )

    @app.get(LEGACY_CAPTURE_PATH)
    async def capture_metadata(
        _claims: Annotated[dict[str, Any], Depends(require_capture)],
    ) -> dict[str, Any]:
        if not capture_runtime.enabled:
            raise HTTPException(status_code=404, detail="Capture is disabled")
        return capture_runtime.catalog.metadata()

    @app.post(LEGACY_CAPTURE_PATH)
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
                debug=_truthy(debug),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        response_headers: dict[str, str] = {}
        resolved_session = (session_id or request.headers.get(CHAT_SESSION_HEADER) or "").strip()
        if resolved_session:
            response_headers[CHAT_SESSION_HEADER] = resolved_session
        return JSONResponse(content=public_result(result), headers=response_headers)

    # The MCP sub-application owns /mcp. It is mounted last so FastAPI routes remain reachable.
    app.mount("/", mcp_app)
    instrument_app(app)
    return app
