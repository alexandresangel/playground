"""Interfaces used by the extraction workflow, independent of SDK clients."""

from typing import Any, Protocol


class ExtractionModel(Protocol):
    deployment: str

    async def extract(
        self, *, prompt: str, document_text: str, temperature: float
    ) -> dict[str, Any]: ...


class ReferenceResolver(Protocol):
    async def resolve_references(self, view_entity: str, trade_xml: str) -> dict[str, Any]: ...
