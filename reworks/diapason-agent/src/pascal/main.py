"""Composition root. Importing this module performs no config, auth, or network I/O."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pascal.adapters.model import AzureModel
from pascal.agent.prompt import PromptProvider
from pascal.agent.service import ChatService
from pascal.api import capture_bridge, chat, sessions, system
from pascal.api.guards import RequestGuards
from pascal.config import limits_from_config, load_config
from pascal.mcp.host import McpHost
from pascal.observability.telemetry import flush_otel, init_otel, instrument_app
from pascal.security.deps import jwt_deps
from pascal.security.setup import build_jwt_auth
from pascal.sessions.blob_store import create_session_store
from pascal.tools.registry import ToolRegistry


def create_app(
    *,
    config=None,
    root=None,
    auth=None,
    model=None,
    store=None,
    transport=None,
    prompt_text=None,
    capture_client=None,
) -> FastAPI:
    project_root = Path(root or os.getenv("PASCAL_ROOT") or Path.cwd())
    cfg = config if config is not None else load_config(project_root)
    limits = limits_from_config(cfg)

    @asynccontextmanager
    async def lifespan(app):
        logging.basicConfig(level=logging.INFO)
        # SDK HTTP request logs can contain URLs; keep them out of application exporters.
        for logger in ("httpx", "httpx2", "httpcore", "httpcore2", "openai", "azure"):
            logging.getLogger(logger).setLevel(logging.WARNING)
        init_otel()
        app.state.ready = False
        app.state.auth = auth or await asyncio.to_thread(build_jwt_auth, project_root, cfg)
        app.state.store = store or await asyncio.to_thread(create_session_store, cfg)
        app.state.prompts = await asyncio.to_thread(PromptProvider, cfg, project_root, prompt_text)
        app.state.model = model or AzureModel(cfg["azure_openai"], limits)
        app.state.transport = transport or McpHost(
            cfg.get("mcp", {}), limits.max_mcp_response_bytes
        )
        app.state.capture_client = capture_client or httpx.AsyncClient(follow_redirects=False)
        app.state.registry = ToolRegistry(
            app.state.transport, limits, cfg.get("ui", {}).get("mention_exclude_tools", [])
        )
        app.state.chat = ChatService(
            model=app.state.model,
            transport=app.state.transport,
            registry=app.state.registry,
            store=app.state.store,
            prompts=app.state.prompts,
            config=cfg,
            limits=limits,
        )
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            await app.state.chat.close()
            if model is None:
                await app.state.model.close()
            if transport is None:
                await app.state.transport.close()
            if capture_client is None:
                await app.state.capture_client.aclose()
            await asyncio.to_thread(flush_otel)

    app = FastAPI(
        title="Pascal — Diapason Agent",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config = cfg

    class AuthProxy:
        def validate(self, *args, **kwargs):
            return app.state.auth.validate(*args, **kwargs)

    deps = jwt_deps(AuthProxy(), config=cfg)
    app.include_router(chat.router(deps))
    app.include_router(sessions.router(deps))
    app.include_router(system.router(deps))
    app.include_router(capture_bridge.router(deps))
    app.add_middleware(
        RequestGuards,
        max_body_bytes=int(cfg.get("capture", {}).get("max_pdf_bytes", 10485760)) + 65536,
    )
    # Default matches legacy integration. Tightening origins requires host inventory first.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.get("cors", {}).get("allow_origins", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[chat.SESSION_HEADER],
    )
    static = project_root / "static"
    if static.is_dir():
        app.mount("/static", StaticFiles(directory=static), name="static")

        @app.get("/", include_in_schema=False)
        async def index():
            return FileResponse(static / "index.html")

    instrument_app(app)
    return app
