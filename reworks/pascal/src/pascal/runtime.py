from __future__ import annotations

from dataclasses import dataclass
from fastapi import HTTPException, Request
from pathlib import Path
from typing import Any, Callable, Dict, Optional
import logging
import sys

from auth_setup import configure_auth
from i18n import LOCALE_HEADER, locale_from_header_value
from session_store import create_session_store
from settings import load_config
import build_info
import telemetry

try:
    from openai import AzureOpenAI
except ImportError:
    AzureOpenAI = None

log = logging.getLogger("diapason.chat")


@dataclass
class Runtime:
    base_dir: Path
    config: dict
    auth: Any
    get_identity: Callable
    require_admin: Callable
    require_refresh: Callable
    require_chat: Callable
    sessions: Any
    tracer: Any = None

    def azure_client(self) -> Optional[Dict[str, Any]]:
        return build_azure_client(self.config)


def create_runtime(base_dir: Path) -> Runtime:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    # Azure SDK / HTTP / OTEL exporter chatter is noisy at INFO.
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry.exporter.otlp.proto.http.trace_exporter").setLevel(
        logging.CRITICAL
    )
    logging.getLogger("opentelemetry.exporter.otlp.proto.http._log_exporter").setLevel(
        logging.WARNING
    )
    # Relocation adapter only: keep local VERSION/config/keystore paths at the project root.
    build_info._VERSION_FILE = base_dir / "VERSION"
    try:
        telemetry.init_otel(logger_name="diapason.chat")
        tracer = telemetry.get_tracer("diapason_agent")
    except Exception:
        tracer = None
    config = load_config(base_dir)
    auth, get_identity, require_admin, require_refresh, require_chat = configure_auth(base_dir, config)
    sessions = create_session_store(config)
    from prompt_loader import init_system_prompt
    init_system_prompt(config, base_dir)
    return Runtime(base_dir, config, auth, get_identity, require_admin, require_refresh, require_chat, sessions, tracer)


def build_azure_client(config: dict) -> Optional[Dict[str, Any]]:
    if AzureOpenAI is None:
        return None
    ao = config.get("azure_openai") if isinstance(config.get("azure_openai"), dict) else {}
    endpoint = str(ao.get("endpoint", "") or "").strip()
    api_key = str(ao.get("api_key", "") or "").strip()
    deployment = str(ao.get("deployment", "") or "").strip()
    api_version = str(ao.get("api_version", "") or "").strip() or "2024-10-21"

    if not endpoint or not api_key or not deployment:
        return None

    return {
        "client": AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        ),
        "deployment": deployment,
    }


def _resolve_session_id(runtime: Runtime, scope: str, session_id: Optional[str]) -> str:
    try:
        return runtime.sessions.resolve_session_id(scope, session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown session_id") from exc


def _session_store_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RuntimeError) and "Azure Blob" in str(exc):
        log.error("session storage: %s", exc, exc_info=exc)
        return HTTPException(status_code=503, detail=str(exc))
    log.exception("session storage unexpected error")
    raise exc


def locale_from_request(request: Request) -> str:
    return locale_from_header_value(request.headers.get(LOCALE_HEADER))
