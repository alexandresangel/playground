"""Save Capture response artifacts without rewriting the original HTTP body."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx


def save_response(response: httpx.Response, output_dir: Path) -> dict[str, Any]:
    """Save one response into a caller-created directory and return safe metadata.

    The caller owns input validation and fresh-directory creation. No request
    headers, URLs, authentication responses, or configuration are recorded.
    """
    try:
        decoded = response.json()
        filename = "response.json"
    except ValueError:
        decoded = None
        filename = "response.body"
    (output_dir / filename).write_bytes(response.content)
    result: dict[str, Any] = {
        "response_sha256": hashlib.sha256(response.content).hexdigest(),
        "artifacts": {"response": filename},
    }
    if not isinstance(decoded, dict):
        return result

    debug = decoded.get("debug")
    extract = debug.get("extract") if isinstance(debug, dict) else None
    extract = extract if isinstance(extract, dict) else {}
    for filename, value in (
        ("trade.xml", decoded.get("trade_xml")),
        ("extracted.xml", extract.get("trade_xml")),
        ("model.xml", extract.get("trade_xml_raw")),
        ("model-response.txt", extract.get("llm_response")),
    ):
        if isinstance(value, str) and value.strip():
            (output_dir / filename).write_bytes(value.encode("utf-8"))
            result["artifacts"][filename] = filename
    for key in ("deployment", "temperature", "prompt_path", "prompt_sha256", "model"):
        if isinstance(extract.get(key), (str, int, float, bool)):
            result[key] = extract[key]
    if isinstance(extract.get("usage"), dict):
        result["usage"] = {
            key: value for key, value in extract["usage"].items()
            if key in (
                "input", "output", "total", "input_tokens", "output_tokens", "total_tokens",
                "cached_tokens", "reasoning_tokens", "prompt_tokens", "completion_tokens",
            ) and isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    return result
