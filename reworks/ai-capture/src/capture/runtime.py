from __future__ import annotations

from dataclasses import dataclass
from fastapi import HTTPException, Request
from pathlib import Path
from typing import Any, Callable, Dict, Optional
import logging
import sys
from openai import AzureOpenAI

import telemetry
from settings import load_config
from auth_setup import configure_auth
import build_info
from capture.workflow.prompts import capture_enabled, init_capture_prompts

log = logging.getLogger("diapason.chat")


@dataclass
class Runtime:
    base_dir: Path
    config: dict
    auth: Any
    get_identity: Callable
    require_refresh: Callable
    require_capture: Callable
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
    # Keep VERSION and local configuration paths at the project root.
    build_info._VERSION_FILE = base_dir / "VERSION"
    try:
        telemetry.init_otel(logger_name="diapason.chat")
        tracer = telemetry.get_tracer("diapason_agent")
    except Exception:
        tracer = None
    config = load_config(base_dir)
    auth, get_identity, require_refresh, require_capture = configure_auth(base_dir, config)
    try:
        if capture_enabled(config):
            init_capture_prompts(config, base_dir)
    except Exception:
        auth.close()
        raise
    return Runtime(base_dir, config, auth, get_identity, require_refresh, require_capture, tracer)


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
