"""Capture's API-only workflow service; no chat application or frontend startup."""

from capture.api import auth, extraction, health, middleware
from capture.runtime import Runtime, create_runtime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import build_info


def create_app(base_dir: Path, *, runtime: Runtime | None = None) -> FastAPI:
    build_info._VERSION_FILE = base_dir / "VERSION"
    runtime = runtime or create_runtime(base_dir)
    app = FastAPI(title="Capture", version=build_info.load()["version"])
    app.state.runtime = runtime
    middleware.configure_middleware(app, runtime)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    for module in (health, auth, extraction):
        app.include_router(module.create_router(runtime))
    return app
