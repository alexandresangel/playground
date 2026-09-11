"""Content-free AI spans."""

from contextlib import contextmanager, nullcontext
from opentelemetry.trace import Status, StatusCode
from time import perf_counter

from telemetry import get_tracer


@contextmanager
def private_graph_run():
    """Keep graph inputs out of automatic LangSmith tracing, even when env-enabled."""
    from langsmith import tracing_context
    with tracing_context(enabled=False):
        yield


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
