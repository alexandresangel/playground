"""Application runtime shared by the HTTP and MCP front doors."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Any

from capture.catalog import PromptCatalog
from capture.config import capture_config, float_setting, integer_setting
from capture.diapason import DiapasonClient
from capture.llm import AzureCaptureLlm
from capture.security import CaptureIdentity
from capture.workflow import CaptureLlm, CaptureWorkflow


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    output = dict(result)
    output.pop("session_artifacts", None)
    output.pop("timings_ms", None)
    return output


class CaptureRuntime:
    def __init__(
        self,
        config: dict[str, Any],
        project_root: Path,
        *,
        catalog: PromptCatalog | None = None,
        llm: CaptureLlm | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.capture_settings = capture_config(config)
        self.catalog = catalog or PromptCatalog(config, project_root)
        self.llm = llm or AzureCaptureLlm(config)
        self.workflow = CaptureWorkflow(self.catalog, self.llm)

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
        timeout = float_setting(self.capture_settings, "diapason_timeout_seconds", 120.0)
        diapason = DiapasonClient(identity.diapason, timeout_seconds=timeout)
        return await self.workflow.run(
            pdf_bytes=pdf_bytes,
            trade_type=trade_type,
            diapason=diapason,
            max_pdf_bytes=self.max_pdf_bytes,
            temperature=float_setting(self.capture_settings, "temperature", 0.5),
            debug=debug,
        )

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
