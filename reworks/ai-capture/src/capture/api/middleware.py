"""api: middleware: company HTTP behavior with explicit runtime dependencies."""

from __future__ import annotations

from contextlib import nullcontext
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind, Status, StatusCode
from uuid import uuid4
import logging
import time

from capture.observability.http import apply_identity_span_attrs, set_span_attr
from capture.runtime import Runtime
from capture.http_contract import CORRELATION_HEADER, CUSTOMER_ID_HEADER, USER_ID_HEADER

log = logging.getLogger("capture")


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
        request.state.correlation_id = request.headers.get(CORRELATION_HEADER, "").strip() or str(uuid4())
        span_cm = (
            runtime.tracer.start_as_current_span(
                "http.request",
                context=extract(request.headers),
                kind=SpanKind.SERVER,
                record_exception=False,
                set_status_on_exception=False,
                attributes={"http.request.method": request.method, "http.method": request.method},
            )
            if runtime.tracer and path.startswith("/api/")
            else nullcontext()
        )
        with span_cm as span:
            if span is not None:
                apply_identity_span_attrs(runtime, 
                    span,
                    customer_id=request.headers.get(CUSTOMER_ID_HEADER),
                    user_id=request.headers.get(USER_ID_HEADER),
                    session_id=request.state.correlation_id,
                )
            try:
                response = await call_next(request)
            except Exception as exc:
                if span is not None:
                    span.set_status(Status(StatusCode.ERROR))
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_attribute("http.response.status_code", 500)
                log.error("%s %s failed error_type=%s", request.method, path, type(exc).__name__)
                raise
            elapsed_ms = (time.perf_counter() - start) * 1000
            if path.startswith("/api/"):
                response.headers[CORRELATION_HEADER] = request.state.correlation_id
            if span is not None:
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("http.response.status_code", response.status_code)
                route = request.scope.get("route")
                if route is not None:
                    span.set_attribute("http.route", route.path)
                if response.status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                session_hdr = response.headers.get(CORRELATION_HEADER)
                if session_hdr:
                    set_span_attr(span, "diapason.session_id", session_hdr)
            if path.startswith("/api/") or response.status_code >= 400:
                log.log(
                    logging.WARNING if response.status_code >= 400 else logging.INFO,
                    "%s %s -> %s (%.0fms)",
                    request.method,
                    path,
                    response.status_code,
                    elapsed_ms,
                )
            return response
