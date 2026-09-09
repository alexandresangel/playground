"""One explicit LangGraph; front doors do not duplicate this workflow."""

from typing import Any

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from opentelemetry.trace import Status, StatusCode

from capture.adapters.catalog import PromptCatalog
from capture.observability.telemetry import operation
from capture.workflow.nodes import (
    emit_result,
    extract_text,
    llm_extract,
    normalize_xml,
    resolve_references,
    select_prompt,
    validate_input,
)
from capture.workflow.ports import ExtractionModel, ReferenceResolver
from capture.workflow.state import CaptureContext, CaptureState


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
    def __init__(self, catalog: PromptCatalog, llm: ExtractionModel) -> None:
        self.catalog = catalog
        self.llm = llm
        self.graph = build_capture_graph()

    async def run(
        self,
        *,
        pdf_bytes: bytes,
        trade_type: str,
        diapason: ReferenceResolver,
        max_pdf_bytes: int,
        temperature: float,
        debug: bool = False,
    ) -> dict[str, Any]:
        # Contract text must not escape through ambient LangSmith settings.
        with tracing_context(enabled=False), operation("capture.run") as span:
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
            if not state["result"].get("success"):
                span.set_status(Status(StatusCode.ERROR))
                span.set_attribute("error.type", "ReferenceResolutionFailed")
        return state["result"]
