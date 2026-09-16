"""Extract trade XML from PDF text via Azure OpenAI."""

from __future__ import annotations

from pypdf import PdfReader
from typing import Any, Dict
import io
import re
import xml.etree.ElementTree as ET

from telemetry import usage_from_completion
from capture.workflow.prompts import get_prompt_text, get_trade_type_config, capture_temperature
from capture.observability.ai import ai_span, record_usage

_PDF_PREVIEW_CHARS = 2000


def validate_pdf_bytes(data: bytes, *, max_bytes: int) -> None:
    if not data:
        raise ValueError("PDF file is empty")
    if len(data) > max_bytes:
        raise ValueError(f"PDF exceeds max size ({max_bytes} bytes)")
    if not data.startswith(b"%PDF-"):
        raise ValueError("File is not a PDF (%PDF- header missing)")


def pdf_to_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("Could not extract text from PDF")
    return text


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def apply_trade_type_shortname(trade_xml: str, trade_type: str) -> str:
    """Set <tradeType shortname="..."/> from the API trade_type (LLM must not choose it)."""
    key = (trade_type or "").strip()
    if not key:
        raise ValueError("trade_type is required")
    try:
        root = ET.fromstring(trade_xml)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid trade XML from LLM: {exc}") from exc

    trade_type_el = None
    for el in root.iter():
        if _local_tag(el.tag) == "tradetype":
            trade_type_el = el
            break
    if trade_type_el is None:
        trade_type_el = ET.SubElement(root, "tradeType")

    trade_type_el.set("shortname", key)
    trade_type_el.text = None
    return ET.tostring(root, encoding="unicode")


def extract_xml_from_llm(text: str) -> str:
    raw = (text or "").strip()
    fence = re.search(r"```(?:xml)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("<")
    if start < 0:
        raise ValueError("LLM response did not contain XML")
    return raw[start:].strip()


def extract_trade_xml_detail(
    pdf_bytes: bytes,
    trade_type: str,
    config: Dict[str, Any],
    azure: Dict[str, Any],
) -> Dict[str, Any]:
    type_cfg = get_trade_type_config(trade_type)
    prompt_blob = type_cfg["prompt_blob"]
    prompt = get_prompt_text(config, prompt_blob)
    document_text = pdf_to_text(pdf_bytes)

    client = azure["client"]
    deployment = str(azure["deployment"]).strip()

    with ai_span("ai.capture.model") as span:
        response = client.chat.completions.create(
            model=deployment,
            temperature=capture_temperature(config),
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Extract the trade as Diapason import XML from this document text. "
                        "Return XML only.\n\n"
                        f"{document_text}"
                    ),
                },
            ],
        )
        record_usage(span, usage_from_completion(response))
    choice = response.choices[0] if response.choices else None
    llm_response = choice.message.content if choice and choice.message else ""
    if not llm_response:
        raise RuntimeError("Empty LLM response for trade XML extraction")

    raw_trade_xml = extract_xml_from_llm(llm_response)
    trade_xml = apply_trade_type_shortname(raw_trade_xml, trade_type)

    return {
        "trade_type": trade_type,
        "prompt_blob": prompt_blob,
        "deployment": deployment,
        "temperature": capture_temperature(config),
        "pdf_text_length": len(document_text),
        "pdf_text_preview": document_text[:_PDF_PREVIEW_CHARS],
        "llm_response": llm_response,
        "trade_xml_raw": raw_trade_xml,
        "trade_xml": trade_xml,
    }


def extract_trade_xml(
    pdf_bytes: bytes,
    trade_type: str,
    config: Dict[str, Any],
    azure: Dict[str, Any],
) -> str:
    return extract_trade_xml_detail(pdf_bytes, trade_type, config, azure)["trade_xml"]