from __future__ import annotations

from contextlib import nullcontext
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response
from opentelemetry.propagate import extract
import logging
import time

from pascal.observability.routing import is_quiet_request

from pascal.observability.http import _apply_identity_span_attrs, _set_span_attr
from pascal.runtime import Runtime

log = logging.getLogger("diapason.chat")
CHAT_SESSION_HEADER = "X-Diapason-Chat-Session"
USER_ID_HEADER = "X-Diapason-User-Id"
CUSTOMER_ID_HEADER = "X-Diapason-Customer-Id"


def configure_middleware(app, runtime: Runtime) -> None:
    router = app

    @router.exception_handler(HTTPException)
    async def log_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        log.warning("%s %s -> %s", request.method, request.url.path, exc.status_code)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @router.exception_handler(RequestValidationError)
    async def log_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        log.warning("%s %s -> 422", request.method, request.url.path)
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @router.middleware("http")
    async def log_requests(request: Request, call_next) -> Response:
        start = time.perf_counter()
        path = request.url.path
        span_cm = (
            runtime.tracer.start_as_current_span(
                "http.request",
                context=extract(request.headers),
                record_exception=False,
                set_status_on_exception=False,
                attributes={"http.method": request.method, "http.route": path},
            )
            if runtime.tracer and path.startswith("/api/")
            else nullcontext()
        )
        with span_cm as span:
            if span is not None:
                _apply_identity_span_attrs(runtime, 
                    span,
                    customer_id=request.headers.get(CUSTOMER_ID_HEADER),
                    user_id=request.headers.get(USER_ID_HEADER),
                    session_id=request.headers.get(CHAT_SESSION_HEADER),
                )
            try:
                response = await call_next(request)
            except Exception as exc:
                log.error("%s %s failed error_type=%s", request.method, path, type(exc).__name__)
                raise
            elapsed_ms = (time.perf_counter() - start) * 1000
            if span is not None:
                span.set_attribute("http.status_code", response.status_code)
                session_hdr = response.headers.get(CHAT_SESSION_HEADER)
                if session_hdr:
                    _set_span_attr(span, "diapason.session_id", session_hdr)
            quiet = is_quiet_request(request) and response.status_code < 400
            if not quiet and (path.startswith("/api/") or response.status_code >= 400):
                log.log(
                    logging.WARNING if response.status_code >= 400 else logging.INFO,
                    "%s %s -> %s (%.0fms)",
                    request.method,
                    path,
                    response.status_code,
                    elapsed_ms,
                )
            return response
