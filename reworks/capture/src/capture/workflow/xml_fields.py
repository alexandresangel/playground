"""Count populated fields in resolved trade XML."""

from __future__ import annotations
import xml.etree.ElementTree as ET


def count_extracted_fields(trade_xml: str) -> int:
    raw = (trade_xml or "").strip()
    if not raw:
        return 0
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return 0
    n = 0
    for el in root.iter():
        if el is root:
            continue
        if (el.attrib.get("shortname") or "").strip():
            n += 1
            continue
        if (el.attrib.get("name") or "").strip():
            n += 1
            continue
        if (el.text or "").strip():
            n += 1
    return n