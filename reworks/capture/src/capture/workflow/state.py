"""Typed execution state and request-scoped runtime dependencies."""

from dataclasses import dataclass
from typing import Any, TypedDict

from capture.adapters.catalog import PromptCatalog
from capture.workflow.ports import ExtractionModel, ReferenceResolver


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
    steps: list[dict[str, Any]]
    result: dict[str, Any]


@dataclass(frozen=True)
class CaptureContext:
    catalog: PromptCatalog
    llm: ExtractionModel
    resolver: ReferenceResolver
    max_pdf_bytes: int
    temperature: float
    debug: bool = False
