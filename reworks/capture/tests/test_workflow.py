from pathlib import Path
from typing import Any

import pytest

from capture.catalog import PromptCatalog
from capture.workflow import CaptureWorkflow


class FakeLlm:
    deployment = "fake-deployment"

    async def extract(
        self, *, prompt: str, document_text: str, temperature: float
    ) -> dict[str, Any]:
        assert "Only generate the xml" in prompt
        assert document_text == "extracted contract text"
        assert temperature == 0.5
        return {
            "content": '<tradeMoneyMarket><entity name="ACME"/></tradeMoneyMarket>',
            "deployment": self.deployment,
            "usage": {"input": 10, "output": 5, "total": 15},
        }


class FakeResolver:
    def __init__(self) -> None:
        self.source_xml = ""

    async def resolve_references(self, view_entity: str, trade_xml: str) -> dict[str, Any]:
        assert view_entity == "loanDeposit"
        self.source_xml = trade_xml
        return {
            "success": True,
            "trade_xml": trade_xml.replace('name="ACME"', 'name="ACME" id="42"'),
            "message": "",
            "warnings": [],
        }


@pytest.mark.asyncio
async def test_graph_runs_unchanged_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = Path(__file__).resolve().parents[1]
    catalog = PromptCatalog({"capture": {"catalog_backend": "filesystem"}}, project_root)
    catalog.initialize()
    resolver = FakeResolver()
    monkeypatch.setattr("capture.workflow.pdf_to_text", lambda _data: "extracted contract text")

    result = await CaptureWorkflow(catalog, FakeLlm()).run(
        pdf_bytes=b"%PDF-test",
        trade_type="iamLoan",
        diapason=resolver,
        max_pdf_bytes=1024,
        temperature=0.5,
        debug=True,
    )

    assert result["success"] is True
    assert result["trade_type"] == "iamLoan"
    assert result["view_entity"] == "loanDeposit"
    assert result["menu_name"] == "loanDeposit"
    assert result["extracted_field_count"] == 2
    assert '<tradeType shortname="iamLoan"' in resolver.source_xml
    assert result["prompt_version"] == "1"
    assert result["usage"]["total"] == 15
    assert result["debug"]["extract"]["pdf_text_preview"] == "extracted contract text"
