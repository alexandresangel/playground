"""Legacy-compatible PDF, LLM, and XML extraction helpers."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET

from pypdf import PdfReader

PDF_PREVIEW_CHARS = 2000


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


def extract_xml_from_llm(text: str) -> str:
    raw = (text or "").strip()
    fence = re.search(r"```(?:xml)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("<")
    if start < 0:
        raise ValueError("LLM response did not contain XML")
    return raw[start:].strip()


def apply_trade_type_shortname(trade_xml: str, trade_type: str) -> str:
    key = (trade_type or "").strip()
    if not key:
        raise ValueError("trade_type is required")
    try:
        root = ET.fromstring(trade_xml)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid trade XML from LLM: {exc}") from exc
    trade_type_element = None
    for element in root.iter():
        if _local_tag(element.tag) == "tradetype":
            trade_type_element = element
            break
    if trade_type_element is None:
        trade_type_element = ET.SubElement(root, "tradeType")
    trade_type_element.set("shortname", key)
    trade_type_element.text = None
    return ET.tostring(root, encoding="unicode")


def count_extracted_fields(trade_xml: str) -> int:
    raw = (trade_xml or "").strip()
    if not raw:
        return 0
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return 0
    count = 0
    for element in root.iter():
        if element is root:
            continue
        if (
            (element.attrib.get("shortname") or "").strip()
            or (element.attrib.get("name") or "").strip()
            or (element.text or "").strip()
        ):
            count += 1
    return count
