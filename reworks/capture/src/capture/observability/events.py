"""Capture-specific operation naming over the reusable telemetry primitives."""

import logging
import time
from contextlib import contextmanager

from capture.observability.telemetry import operation

log = logging.getLogger("capture.workflow")


@contextmanager
def node_span(name: str, state: dict):
    started = time.perf_counter()
    with operation(f"capture.{name}", attributes={"capture.node": name}) as span:
        try:
            yield span
        except BaseException as exc:
            log.warning("node=%s status=failed error_type=%s", name, type(exc).__name__)
            raise
        finally:
            log.info("node=%s duration_ms=%d", name, int((time.perf_counter() - started) * 1000))
