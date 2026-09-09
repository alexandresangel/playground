"""Direct Diapason REST client adapted from diapason-mcp's resolveReferences path."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True)
class DiapasonRequestContext:
    base_url: str
    scope: int
    api_token: str = field(repr=False)
    api_token_type: str = "Bearer"


log = logging.getLogger("diapason.integrations.rest")


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_child(parent: ET.Element, local_name: str) -> ET.Element | None:
    wanted = local_name.lower()
    return next(
        (child for child in parent if _local_tag(child.tag).lower() == wanted),
        None,
    )


def _text_child(parent: ET.Element, local_name: str) -> str:
    element = _find_child(parent, local_name)
    return "" if element is None or element.text is None else element.text.strip()


def wrap_trade_xml(trade_xml: str) -> str:
    value = trade_xml.strip()
    return value if value.startswith("<list>") else f"<list>{value}</list>"


def _unwrap_cdata(text: str) -> str:
    value = text.strip()
    return value[9:-3] if value.startswith("<![CDATA[") and value.endswith("]]>") else value


def parse_resolve_references_result(xml_text: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError(f"Invalid XML from Diapason resolveReferences: {exc}") from exc
    basic = (
        root
        if _local_tag(root.tag).lower() == "basicresponse"
        else next(
            (item for item in root.iter() if _local_tag(item.tag).lower() == "basicresponse"),
            None,
        )
    )
    if basic is None:
        raise RuntimeError("No basicResponse element in Diapason response")
    success = _text_child(basic, "success").lower() == "true"
    message = _text_child(basic, "message")
    warnings = [line.strip() for line in message.splitlines() if line.strip()]
    if not success and message and message not in warnings:
        warnings.insert(0, message)
    return {
        "success": success,
        "trade_xml": _unwrap_cdata(_text_child(basic, "extraInfo")).strip(),
        "message": message,
        "warnings": warnings,
    }


class DiapasonClient:
    def __init__(self, context: DiapasonRequestContext, *, timeout_seconds: float = 120.0) -> None:
        self._context = context
        self._timeout = timeout_seconds

    async def resolve_references(self, view_entity: str, trade_xml: str) -> dict[str, Any]:
        url = f"{self._context.base_url}/api/v2/importData/resolveReferences"
        headers = {
            "Authorization": f"{self._context.api_token_type} {self._context.api_token}",
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            from opentelemetry import propagate

            propagate.inject(headers)
        except Exception:  # pragma: no cover - OTel is optional at runtime
            pass
        form = {
            "importService": view_entity,
            "scope": str(self._context.scope),
            "data": wrap_trade_xml(trade_xml),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, data=form, headers=headers)
                if response.status_code != 200:
                    log.warning(
                        "resolveReferences non-200; retrying once status=%s host=%s",
                        response.status_code,
                        httpx.URL(url).host,
                    )
                    response = await client.post(url, data=form, headers=headers)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Diapason resolveReferences timed out after {self._timeout:.0f}s"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Diapason resolveReferences HTTP error: {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError("Diapason resolveReferences request failed") from exc
        result = parse_resolve_references_result(response.text)
        result["view_entity"] = view_entity
        return result
