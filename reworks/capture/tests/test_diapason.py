from urllib.parse import parse_qs

import httpx
import pytest
import respx

from capture.adapters.diapason import (
    DiapasonClient,
    parse_resolve_references_result,
    wrap_trade_xml,
)
from capture.auth import DiapasonRequestContext


def test_wrap_trade_xml() -> None:
    assert wrap_trade_xml("<trade/>") == "<list><trade/></list>"
    assert wrap_trade_xml("<list><trade/></list>") == "<list><trade/></list>"


def test_parse_resolve_success() -> None:
    body = """
    <basicResponse>
      <success>true</success>
      <message>Reference warning</message>
      <extraInfo>&lt;tradeMoneyMarket&gt;&lt;entity id="1"/&gt;&lt;/tradeMoneyMarket&gt;</extraInfo>
    </basicResponse>
    """
    result = parse_resolve_references_result(body)
    assert result["success"] is True
    assert 'id="1"' in result["trade_xml"]
    assert result["warnings"] == ["Reference warning"]


def test_parse_resolve_failure() -> None:
    body = """
    <basicResponse>
      <success>false</success>
      <message>Technical error</message>
      <extraInfo></extraInfo>
    </basicResponse>
    """
    result = parse_resolve_references_result(body)
    assert result == {
        "success": False,
        "trade_xml": "",
        "message": "Technical error",
        "warnings": ["Technical error"],
    }


@pytest.mark.asyncio
@respx.mock
async def test_direct_client_uses_legacy_form_and_auth() -> None:
    route = respx.post("https://diapason.test/api/v2/importData/resolveReferences").mock(
        return_value=httpx.Response(
            200,
            text=(
                "<basicResponse><success>true</success><message></message>"
                "<extraInfo>&lt;trade/&gt;</extraInfo></basicResponse>"
            ),
        )
    )
    client = DiapasonClient(
        DiapasonRequestContext(
            base_url="https://diapason.test",
            scope=22,
            api_token="secret-token",
        )
    )

    result = await client.resolve_references("loanDeposit", "<trade/>")

    assert result["success"] is True
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret-token"
    form = parse_qs(request.content.decode())
    assert form == {
        "importService": ["loanDeposit"],
        "scope": ["22"],
        "data": ["<list><trade/></list>"],
    }


@pytest.mark.asyncio
@respx.mock
async def test_direct_client_preserves_one_retry() -> None:
    route = respx.post("https://diapason.test/api/v2/importData/resolveReferences").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(
                200,
                text=(
                    "<basicResponse><success>true</success><message></message>"
                    "<extraInfo>&lt;trade/&gt;</extraInfo></basicResponse>"
                ),
            ),
        ]
    )
    client = DiapasonClient(
        DiapasonRequestContext(
            base_url="https://diapason.test",
            scope=22,
            api_token="secret-token",
        )
    )

    assert (await client.resolve_references("loanDeposit", "<trade/>"))["success"] is True
    assert route.call_count == 2
