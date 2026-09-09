"""The seven business stages; PDF/XML/prompt behavior follows the current implementation."""

import asyncio
import logging
import time
from typing import Any

from langgraph.runtime import Runtime

from capture.observability.events import node_span
from capture.observability.telemetry import record_model_usage
from capture.workflow.extraction import (
    PDF_PREVIEW_CHARS,
    apply_trade_type_shortname,
    count_extracted_fields,
    extract_xml_from_llm,
    pdf_to_text,
    validate_pdf_bytes,
)
from capture.workflow.state import CaptureContext, CaptureState

log = logging.getLogger("capture.workflow")


def _timing(state: CaptureState, key: str, started: float) -> dict[str, int]:
    timings = dict(state.get("timings_ms") or {})
    timings[key] = int((time.perf_counter() - started) * 1000)
    return timings


async def validate_input(state: CaptureState, runtime: Runtime[CaptureContext]) -> dict[str, Any]:
    started = time.perf_counter()
    with node_span("validate_input", state):
        validate_pdf_bytes(state["pdf_bytes"], max_bytes=runtime.context.max_pdf_bytes)
        if not state.get("trade_type", "").strip():
            raise ValueError("trade_type is required")
    return {
        "trade_type": state["trade_type"].strip(),
        "timings_ms": _timing(state, "validate", started),
    }


async def extract_text(state: CaptureState) -> dict[str, Any]:
    started = time.perf_counter()
    with node_span("extract_text", state):
        document_text = await asyncio.to_thread(pdf_to_text, state["pdf_bytes"])
    return {"document_text": document_text, "timings_ms": _timing(state, "parse_pdf", started)}


async def select_prompt(state: CaptureState, runtime: Runtime[CaptureContext]) -> dict[str, Any]:
    started = time.perf_counter()
    with node_span("select_prompt", state):
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
    with node_span("llm_extract", state) as span:
        response = await runtime.context.llm.extract(
            prompt=state["prompt"],
            document_text=state["document_text"],
            temperature=state["temperature"],
        )
        record_model_usage(response.get("usage") or {})
        if span is not None:
            usage = response.get("usage") or {}
            span.set_attribute("gen_ai.provider.name", "azure.ai.openai")
            span.set_attribute("gen_ai.operation.name", "chat")
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
    with node_span("normalize_xml", state):
        raw = extract_xml_from_llm(state["llm_response"])
        source = apply_trade_type_shortname(raw, state["trade_type"])
        timings = _timing(state, "normalize", started)
        extract_ms = sum(
            timings.get(key, 0)
            for key in ("parse_pdf", "select_prompt", "llm_extract", "normalize")
        )
        steps = [
            {
                "operation": "extract_xml",
                "duration_ms": extract_ms,
                "metadata": {
                    "trade_type": state["trade_type"],
                    "prompt_blob": state["prompt_blob"],
                },
            }
        ]
    return {
        "raw_trade_xml": raw,
        "source_trade_xml": source,
        "timings_ms": timings,
        "steps": steps,
    }


async def resolve_references(
    state: CaptureState, runtime: Runtime[CaptureContext]
) -> dict[str, Any]:
    started = time.perf_counter()
    with node_span("resolve_references", state) as span:
        body = await runtime.context.resolver.resolve_references(
            state["view_entity"], state["source_trade_xml"]
        )
        if span is not None:
            span.set_attribute("diapason.view_entity", state["view_entity"])
            span.set_attribute("diapason.resolve.success", bool(body.get("success")))
        timings = _timing(state, "resolve", started)
        trace = list(state.get("steps") or [])
        trace.append(
            {
                "operation": "resolveReferences",
                "duration_ms": timings["resolve"],
                "metadata": {
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
        "steps": trace,
    }


async def emit_result(state: CaptureState, runtime: Runtime[CaptureContext]) -> dict[str, Any]:
    with node_span("emit_result", state):
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

        result: dict[str, Any] = {
            "success": success,
            "trade_xml": resolved_xml,
            "view_entity": state["view_entity"],
            "menu_name": state["menu_name"],
            "trade_type": state["trade_type"],
            "extracted_field_count": count_extracted_fields(resolved_xml) if success else 0,
            "message": message,
            "warnings": state.get("warnings") or [],
            "steps": state.get("steps") or [],
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
            result["debug"] = {
                "extract": extract_detail,
                "resolve_references": body,
                "resolve_references_request": {
                    "view_entity": state["view_entity"],
                    "trade_xml": state["source_trade_xml"],
                },
            }
    return {"result": result}
