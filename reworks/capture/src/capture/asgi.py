"""Uvicorn entry point."""

import logging
import os

from capture.app import create_app
from capture.telemetry import init_otel

logging.basicConfig(
    level=logging.DEBUG
    if os.getenv("CAPTURE_DEBUG", "").lower() in {"1", "true", "yes"}
    else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
for noisy_logger in ("azure", "httpx", "httpcore", "openai", "mcp.server"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

init_otel()
app = create_app()
