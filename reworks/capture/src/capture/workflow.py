"""The Capture LangGraph workflow: legacy logic, explicit operational boundaries."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from capture.catalog import PromptCatalog
from capture.diapason import DiapasonClient
from capture.extraction import (
    PDF_PREVIEW_CHARS,
    apply_trade_type_shortname,
    count_extracted_fields,
    extract_xml_from_llm,
    pdf_to_text,
    validate_pdf_bytes,
)

log = logging.getLogger("capture.workflow")


class CaptureLlm(Protocol):
    deployment: str

    async def extract(
        self, *, prompt: str, document_text: str, temperature: float
    ) -> dict[str, Any]: ...


class ReferenceResolver(Protocol):
    async def resolve_references(self, view_entity: str, trade_xml: str) -> dict[str, Any]: ...


class CaptureState(TypedDict, total=False):
    pdf_bytes: bytes
    trade_type: str
    document_text: str
    prompt_blob: str
    prompt: str
    prompt_version: str
    view_entity: str
    menu_name: str
    temperature: float
    llm_response: str
    model: str
    usage: dict[str, int]
    raw_trade_xml: str
    source_trade_xml: str
    resolve_body: dict[str, Any]
    warnings: list[str]
    timings_ms: dict[str, int]
    tool_trace: list[dict[str, Any]]
    result: dict[str, Any]


@dataclass(frozen=True)
class CaptureContext:
    catalog: PromptCatalog
    llm: CaptureLlm
    resolver: ReferenceResolver
    max_pdf_bytes: int
    temperature: float
    debug: bool = False


def _tracer() -> object | None:
    try:
        from opentelemetry import trace

        return trace.get_tracer("capture.workflow")
    except Exception:  # pragma: no cover - optional observability
        return None


@contextmanager
def _node_span(name: str, state: CaptureState) -> Iterator[object | None]:
    tracer = _tracer()
    attributes = {"capture.node": name}
    if state.get("trade_type"):
        attributes["capture.trade_type"] = state["trade_type"]
    manager = (
        tracer.start_as_current_span(f"capture.{name}", attributes=attributes)
        if tracer
        else nullcontext()
    )
    started = time.perf_counter()
    log.info("node=%s event=start trade_type=%s", name, state.get("trade_type", ""))
    with manager as span:
        try:
            yield span
        except Exception as exc:
            if span is not None:
                span.record_exception(exc)
            log.warning(
                "node=%s event=failed duration_ms=%d error_type=%s",
                name,
                int((time.perf_counter() - started) * 1000),
                type(exc).__name__,
            )
            raise
        log.info(
            "node=%s event=completed duration_ms=%d",
            name,
            int((time.perf_counter() - started) * 1000),
        )


def _timing(state: CaptureState, key: str, started: float) -> dict[str, int]:
    timings = dict(state.get("timings_ms") or {})
    timings[key] = int((time.perf_counter() - started) * 1000)
    return timings


async def validate_input(state: CaptureState, runtime: Runtime[CaptureContext]) -> dict[str, Any]:
    started = time.perf_counter()
    with _node_span("validate_input", state):
        validate_pdf_bytes(state["pdf_bytes"], max_bytes=runtime.context.max_pdf_bytes)
        if not state.get("trade_type", "").strip():
            raise ValueError("trade_type is required")
    return {
        "trade_type": state["trade_type"].strip(),
        "timings_ms": _timing(state, "validate", started),
    }


async def extract_text(state: CaptureState) -> dict[str, Any]:
    started = time.perf_counter()
    with _node_span("extract_text", state):
        document_text = await asyncio.to_thread(pdf_to_text, state["pdf_bytes"])
    return {"document_text": document_text, "timings_ms": _timing(state, "parse_pdf", started)}


async def select_prompt(state: CaptureState, runtime: Runtime[CaptureContext]) -> dict[str, Any]:
    started = time.perf_counter()
    with _node_span("select_prompt", state):
        type_config = runtime.context.catalog.trade_type_config(state["trade_type"])
        prompt = await asyncio.to_thread(
            runtime.context.catalog.prompt_text, type_config["prompt_blob"]
        )
    return {
        "prompt_blob": type_config["prompt_blob"],
        "prompt": prompt,
        "prompt_version": runtime.context.catalog.version,
        "view_entity": type_config.get("view_entity") or "loanDeposit",
        "menu_name": type_config.get("menu_name")
        or type_config.get("view_entity")
        or "loanDeposit",
        "temperature": runtime.context.temperature,
        "timings_ms": _timing(state, "select_prompt", started),
    }


async def llm_extract(state: CaptureState, runtime: Runtime[CaptureContext]) -> dict[str, Any]:
    started = time.perf_counter()
    with _node_span("llm_extract", state) as span:
        response = await runtime.context.llm.extract(
            prompt=state["prompt"],
            document_text=state["document_text"],
            temperature=state["temperature"],
        )
        if span is not None:
            usage = response.get("usage") or {}
            span.set_attribute("gen_ai.system", "azure.openai")
            span.set_attribute("gen_ai.request.model", str(response.get("deployment") or ""))
            span.set_attribute("gen_ai.usage.input_tokens", int(usage.get("input", 0)))
            span.set_attribute("gen_ai.usage.output_tokens", int(usage.get("output", 0)))
    return {
        "llm_response": str(response["content"]),
        "model": str(response.get("deployment") or runtime.context.llm.deployment),
        "usage": dict(response.get("usage") or {}),
        "timings_ms": _timing(state, "llm_extract", started),
    }


async def normalize_xml(state: CaptureState) -> dict[str, Any]:
    started = time.perf_counter()
    with _node_span("normalize_xml", state):
        raw = extract_xml_from_llm(state["llm_response"])
        source = apply_trade_type_shortname(raw, state["trade_type"])
        timings = _timing(state, "normalize", started)
        extract_ms = sum(
            timings.get(key, 0)
            for key in ("parse_pdf", "select_prompt", "llm_extract", "normalize")
        )
        tool_trace = [
            {
                "name": "intelligence-contract",
                "tool": "extract_xml",
                "mcp_label": "Intelligence contract",
                "duration_ms": extract_ms,
                "arguments": {
                    "trade_type": state["trade_type"],
                    "prompt_blob": state["prompt_blob"],
                },
            }
        ]
    return {
        "raw_trade_xml": raw,
        "source_trade_xml": source,
        "timings_ms": timings,
        "tool_trace": tool_trace,
    }


async def resolve_references(
    state: CaptureState, runtime: Runtime[CaptureContext]
) -> dict[str, Any]:
    started = time.perf_counter()
    with _node_span("resolve_references", state) as span:
        body = await runtime.context.resolver.resolve_references(
            state["view_entity"], state["source_trade_xml"]
        )
        if span is not None:
            span.set_attribute("diapason.view_entity", state["view_entity"])
            span.set_attribute("diapason.resolve.success", bool(body.get("success")))
        timings = _timing(state, "resolve", started)
        trace = list(state.get("tool_trace") or [])
        trace.append(
            {
                "name": "resolveReferences",
                "tool": "resolveReferences",
                "mcp_server": "default",
                "mcp_label": "Diapason",
                "transport": "direct_http",
                "duration_ms": timings["resolve"],
                "arguments": {
                    "view_entity": state["view_entity"],
                    "menu_name": state["menu_name"],
                    "trade_type": state["trade_type"],
                },
            }
        )
    return {
        "resolve_body": body,
        "warnings": [str(item) for item in body.get("warnings", []) if item],
        "timings_ms": timings,
        "tool_trace": trace,
    }


async def emit_result(state: CaptureState, runtime: Runtime[CaptureContext]) -> dict[str, Any]:
    with _node_span("emit_result", state):
        body = state["resolve_body"]
        success = bool(body.get("success"))
        resolved_xml = str(body.get("trade_xml") or "").strip()
        message = str(body.get("message") or "")
        if success and not resolved_xml:
            success = False
            message = message or "resolveReferences returned success but no trade_xml"
        if not success:
            log.warning(
                "capture resolution failed trade_type=%s view_entity=%s",
                state["trade_type"],
                state["view_entity"],
            )

        extract_detail = {
            "trade_type": state["trade_type"],
            "prompt_blob": state["prompt_blob"],
            "deployment": state["model"],
            "temperature": state["temperature"],
            "pdf_text_length": len(state["document_text"]),
            "pdf_text_preview": state["document_text"][:PDF_PREVIEW_CHARS],
            "llm_response": state["llm_response"],
            "trade_xml_raw": state["raw_trade_xml"],
            "trade_xml": state["source_trade_xml"],
        }
        result: dict[str, Any] = {
            "success": success,
            "trade_xml": resolved_xml,
            "view_entity": state["view_entity"],
            "menu_name": state["menu_name"],
            "trade_type": state["trade_type"],
            "extracted_field_count": count_extracted_fields(resolved_xml) if success else 0,
            "message": message,
            "warnings": state.get("warnings") or [],
            "tool_trace": state.get("tool_trace") or [],
            "session_artifacts": {
                "extract": extract_detail,
                "resolve_references": body,
                "source_trade_xml": state["source_trade_xml"],
                "resolved_trade_xml": resolved_xml,
            },
            "timings_ms": {
                "extract": sum(
                    state.get("timings_ms", {}).get(key, 0)
                    for key in ("parse_pdf", "select_prompt", "llm_extract", "normalize")
                ),
                "resolve": state.get("timings_ms", {}).get("resolve", 0),
            },
            "prompt_version": state["prompt_version"],
            "model": state["model"],
            "usage": state.get("usage") or {},
        }
        if runtime.context.debug:
            result["debug"] = {
                "extract": extract_detail,
                "resolve_references": body,
                "resolve_references_request": {
                    "view_entity": state["view_entity"],
                    "trade_xml": state["source_trade_xml"],
                },
            }
    return {"result": result}


def build_capture_graph():
    builder = StateGraph(CaptureState, context_schema=CaptureContext)
    builder.add_node("validate_input", validate_input)
    builder.add_node("extract_text", extract_text)
    builder.add_node("select_prompt", select_prompt)
    builder.add_node("llm_extract", llm_extract)
    builder.add_node("normalize_xml", normalize_xml)
    builder.add_node("resolve_references", resolve_references)
    builder.add_node("emit_result", emit_result)
    builder.add_edge(START, "validate_input")
    builder.add_edge("validate_input", "extract_text")
    builder.add_edge("extract_text", "select_prompt")
    builder.add_edge("select_prompt", "llm_extract")
    builder.add_edge("llm_extract", "normalize_xml")
    builder.add_edge("normalize_xml", "resolve_references")
    builder.add_edge("resolve_references", "emit_result")
    builder.add_edge("emit_result", END)
    return builder.compile()


class CaptureWorkflow:
    def __init__(self, catalog: PromptCatalog, llm: CaptureLlm) -> None:
        self.catalog = catalog
        self.llm = llm
        self.graph = build_capture_graph()

    async def run(
        self,
        *,
        pdf_bytes: bytes,
        trade_type: str,
        diapason: DiapasonClient,
        max_pdf_bytes: int,
        temperature: float,
        debug: bool = False,
    ) -> dict[str, Any]:
        state = await self.graph.ainvoke(
            {"pdf_bytes": pdf_bytes, "trade_type": trade_type},
            context=CaptureContext(
                catalog=self.catalog,
                llm=self.llm,
                resolver=diapason,
                max_pdf_bytes=max_pdf_bytes,
                temperature=temperature,
                debug=debug,
            ),
        )
        return state["result"]
