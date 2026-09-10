"""Content-free AI spans on the existing company OpenTelemetry provider."""

from contextlib import contextmanager, nullcontext
from langsmith import tracing_context
from opentelemetry.trace import Status, StatusCode
from telemetry import get_tracer
from time import perf_counter


@contextmanager
def ai_span(name: str):
    """Callers use fixed stage names; never record exception messages or inputs."""
    tracer = get_tracer("diapason.ai")
    cm = tracer.start_as_current_span(
        name, record_exception=False, set_status_on_exception=False
    ) if tracer else nullcontext()
    started = perf_counter()
    with cm as span:
        outcome = "success"
        try:
            yield span
        except BaseException:
            outcome = "error"
            if span:
                span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            if span:
                span.set_attribute("ai.outcome", outcome)
                span.set_attribute("ai.duration_ms", (perf_counter() - started) * 1000)


def record_usage(span, usage: dict) -> None:
    if span:
        for key in ("input", "output", "total"):
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                span.set_attribute(f"gen_ai.usage.{key}_tokens", value)


@contextmanager
def private_graph_run():
    """Prevent automatic LangSmith export of graph inputs/state, even if enabled by env."""
    with tracing_context(enabled=False):
        yield
