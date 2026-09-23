from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

import build_info
from capture.api import extraction, health, middleware
from capture.runtime import Runtime, create_runtime
from capture.http_contract import EXPOSED_RESPONSE_HEADERS


def create_app(base_dir: Path, *, runtime: Runtime | None = None) -> FastAPI:
    build_info._VERSION_FILE = base_dir / "VERSION"
    runtime = runtime or create_runtime(base_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            runtime.auth.close()

    app = FastAPI(title="Capture", version=build_info.load()["version"], lifespan=lifespan)
    app.state.runtime = runtime
    middleware.configure_middleware(app, runtime)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=EXPOSED_RESPONSE_HEADERS,
    )
    for module in (health, extraction):
        app.include_router(module.create_router(runtime))
    return app