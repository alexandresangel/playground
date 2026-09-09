"""Composition root: the HTTP application optionally hosts the Capture MCP adapter."""

import asyncio
import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from capture.api.guards import RequestGuards
from capture.api.http import create_router
from capture.auth import CaptureSecurity, build_security
from capture.config import load_config
from capture.observability.telemetry import flush_otel, init_otel, instrument_app
from capture.workflow.service import CaptureRuntime


def create_app(
    *,
    config: dict[str, Any] | None = None,
    runtime: CaptureRuntime | None = None,
    security: CaptureSecurity | None = None,
    project_root: Path | None = None,
) -> FastAPI:
    root = project_root or Path(os.getenv("CAPTURE_ROOT") or Path.cwd())
    settings = config if config is not None else load_config(root)
    capture_runtime = runtime or CaptureRuntime(settings, root)
    capture_security = security or build_security(root, settings)
    mcp = None
    if settings.get("mcp", {}).get("enabled", True):
        # HTTP-only deployments do not import or initialize the server adapter.
        from capture.api.mcp import create_mcp_server

        mcp = create_mcp_server(capture_runtime, capture_security, settings)

    @asynccontextmanager
    async def lifespan(_app):
        logging.basicConfig(level=logging.INFO)
        for name in ("azure", "httpx", "httpx2", "httpcore", "httpcore2", "openai", "mcp"):
            logging.getLogger(name).setLevel(logging.WARNING)
        init_otel("capture")
        try:
            await asyncio.to_thread(capture_runtime.initialize)
            async with AsyncExitStack() as stack:
                if mcp is not None:
                    await stack.enter_async_context(mcp.session_manager.run())
                yield
        finally:
            if runtime is None:
                await capture_runtime.close()
            await asyncio.to_thread(flush_otel)

    app = FastAPI(
        title="Diapason Capture",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.capture_runtime = capture_runtime
    app.state.capture_security = capture_security
    app.include_router(create_router(capture_runtime, capture_security))
    # Includes base64 expansion for the MCP front door, before JSON/multipart parsing.
    app.add_middleware(
        RequestGuards, max_body_bytes=((capture_runtime.max_pdf_bytes + 2) // 3) * 4 + 65536
    )
    if mcp is not None:
        # Mount last; the sub-application owns /mcp, not the business workflow.
        app.mount("/", mcp.streamable_http_app())
    instrument_app(app)
    return app
