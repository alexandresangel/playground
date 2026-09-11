from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging

from prompt_loader import prompt_source
import build_info
from pascal.api import auth, capture, chat, health, middleware, sessions
from pascal.runtime import Runtime, create_runtime


def create_app(base_dir: Path, *, runtime: Runtime | None = None) -> FastAPI:
    build_info._VERSION_FILE = base_dir / "VERSION"
    runtime = runtime or create_runtime(base_dir)
    app = FastAPI(title="Diapason Agent", version=build_info.load()["version"])
    app.state.runtime = runtime
    middleware.configure_middleware(app, runtime)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")
    for module in (health, capture, auth, chat, sessions):
        app.include_router(module.create_router(runtime))

    @app.on_event("startup")
    def started() -> None:
        logging.getLogger("diapason.chat").info(
            "started sessions_backend=%s blob_credential=%s prompt_source=%s",
            getattr(runtime.sessions, "backend", "unknown"),
            getattr(runtime.sessions, "_credential_source", "unknown"),
            prompt_source(),
        )

    return app

