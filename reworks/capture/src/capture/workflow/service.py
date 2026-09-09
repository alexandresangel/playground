"""Application runtime shared by the HTTP and MCP front doors."""

from __future__ import annotations

import asyncio
import base64
import binascii
from pathlib import Path
from typing import Any

from capture.adapters.catalog import PromptCatalog
from capture.adapters.diapason import DiapasonClient
from capture.adapters.model import CaptureModel
from capture.auth import CaptureIdentity
from capture.config import capture_config, float_setting, integer_setting
from capture.workflow.graph import CaptureWorkflow
from capture.workflow.ports import ExtractionModel


class CaptureRuntime:
    def __init__(
        self,
        config: dict[str, Any],
        project_root: Path,
        *,
        catalog: PromptCatalog | None = None,
        llm: ExtractionModel | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.capture_settings = capture_config(config)
        self.catalog = catalog or PromptCatalog(config, project_root)
        self.llm = llm or (CaptureModel(config) if self.enabled else None)
        self._owns_llm = llm is None
        self.workflow = CaptureWorkflow(self.catalog, self.llm) if self.llm is not None else None

    async def close(self) -> None:
        if self._owns_llm and self.llm is not None:
            await self.llm.close()

    @property
    def enabled(self) -> bool:
        return self.capture_settings.get("enabled") is not False

    @property
    def max_pdf_bytes(self) -> int:
        return integer_setting(self.capture_settings, "max_pdf_bytes", 10 * 1024 * 1024)

    def initialize(self) -> None:
        if self.enabled:
            self.catalog.initialize()

    async def execute(
        self,
        *,
        pdf_bytes: bytes,
        trade_type: str,
        identity: CaptureIdentity,
        debug: bool = False,
    ) -> dict[str, Any]:
        if not self.enabled or self.workflow is None:
            raise ValueError("Capture is disabled")
        timeout = float_setting(self.capture_settings, "diapason_timeout_seconds", 120.0)
        diapason = DiapasonClient(identity.diapason, timeout_seconds=timeout)
        try:
            async with asyncio.timeout(
                float_setting(self.capture_settings, "turn_timeout_seconds", 210)
            ):
                return await self.workflow.run(
                    pdf_bytes=pdf_bytes,
                    trade_type=trade_type,
                    diapason=diapason,
                    max_pdf_bytes=self.max_pdf_bytes,
                    temperature=float_setting(self.capture_settings, "temperature", 0.5),
                    debug=debug,
                )
        except TimeoutError as exc:
            raise RuntimeError("Capture turn timed out") from exc

    def decode_pdf_base64(self, value: str) -> bytes:
        raw = (value or "").strip()
        if not raw:
            raise ValueError("pdf_base64 is required")
        if raw.startswith("data:"):
            prefix, separator, raw = raw.partition(",")
            if not separator or ";base64" not in prefix.lower():
                raise ValueError("PDF data URI must use base64 encoding")
        maximum_encoded = ((self.max_pdf_bytes + 2) // 3) * 4 + 8
        if len(raw) > maximum_encoded:
            raise ValueError(f"PDF exceeds max size ({self.max_pdf_bytes} bytes)")
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("pdf_base64 is not valid base64") from exc
        if len(decoded) > self.max_pdf_bytes:
            raise ValueError(f"PDF exceeds max size ({self.max_pdf_bytes} bytes)")
        return decoded
