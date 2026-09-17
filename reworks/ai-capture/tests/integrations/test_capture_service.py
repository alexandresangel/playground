"""Real HTTP/JWT -> graph -> PDF/model -> MCP protocol -> public result."""

import json
import xml.etree.ElementTree as ET

import httpx
import pytest
from cryptography.fernet import Fernet

import mcp_rpc
from capture.workflow import graph


@pytest.mark.parametrize("path", ["/api/capture", "/api/skills/intelligence-contract"])
def test_authenticated_pdf_upload_runs_full_capture_pipeline(
    service, workflow, mcp_transport, monkeypatch, path
):
    monkeypatch.setattr(service.runtime, "azure_client", lambda: workflow.azure)
    monkeypatch.setattr(graph, "mcp_call_tool_json", mcp_rpc.mcp_call_tool_json)
    calls = []
    resolved_xml = (
        '<trade><tradeType shortname="commercialLease">42</tradeType><amount>456</amount></trade>'
    )

    def resolve(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": json.loads(request.content)["id"],
                "result": {
                    "structuredContent": {
                        "success": True,
                        "trade_xml": resolved_xml,
                        "warnings": ["review"],
                    }
                },
            },
        )

    factory = mcp_transport(resolve)
    response = service.client.post(
        path,
        headers=service.headers,
        data={"trade_type": " commercialLease ", "session_id": "caller-session", "debug": "true"},
        files={"pdf": ("contract.pdf", workflow.pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["trade_xml"] == resolved_xml
    assert body["trade_type"] == "commercialLease"
    assert body["view_entity"] == "loanDeposit"
    assert body["menu_name"] == "commercialLease"
    assert body["extracted_field_count"] == 2
    assert body["warnings"] == ["review"]
    assert response.headers["X-Diapason-Chat-Session"] == "caller-session"
    assert "timings_ms" not in body and "session_artifacts" not in body
    workflow.completion.assert_called_once()
    workflow.azure["client"].close.assert_called_once()
    factory.assert_called_once_with(timeout=180.0)
    assert len(calls) == 1
    request = calls[0]
    payload = json.loads(request.content)
    assert payload["params"]["name"] == "resolveReferences"
    arguments = payload["params"]["arguments"]
    assert arguments == body["debug"]["resolve_references_request"]
    assert set(arguments) == {"view_entity", "trade_xml"}
    assert (
        ET.fromstring(arguments["trade_xml"]).find("tradeType").get("shortname")
        == "commercialLease"
    )
    encrypted = request.headers["Authorization"].removeprefix("Bearer ")
    credentials = json.loads(
        Fernet(service.runtime.config["mcp"]["default"]["config_key"]).decrypt(encrypted.encode())
    )
    assert credentials == {
        "base_url": "https://company.example",
        "scope": 3,
        "api_token": "private-api-token",
    }


@pytest.mark.parametrize(
    "failure,status,model_calls,resolver_calls",
    [
        ("invalid-pdf", 400, 0, 0),
        ("empty-model", 502, 1, 0),
        ("invalid-xml", 400, 1, 0),
        ("resolver-http", 502, 1, 1),
        ("resolver-tool", 502, 1, 1),
        ("unresolved", 200, 1, 1),
    ],
)
def test_pipeline_failure_status_and_client_cleanup(
    service, workflow, mcp_transport, monkeypatch, failure, status, model_calls, resolver_calls
):
    monkeypatch.setattr(service.runtime, "azure_client", lambda: workflow.azure)
    monkeypatch.setattr(graph, "mcp_call_tool_json", mcp_rpc.mcp_call_tool_json)
    calls = []

    def resolve(request):
        calls.append(request)
        if failure == "resolver-http":
            return httpx.Response(503)
        result = (
            {"isError": True, "content": [{"text": "unavailable"}]}
            if failure == "resolver-tool"
            else {
                "structuredContent": {
                    "success": False,
                    "message": "unresolved",
                    "warnings": ["missing reference"],
                }
            }
        )
        return httpx.Response(200, json={"result": result})

    mcp_transport(resolve)
    if failure in ("empty-model", "invalid-xml"):
        workflow.completion.return_value.choices[0].message.content = (
            "" if failure == "empty-model" else "<broken"
        )
    pdf = b"not a PDF" if failure == "invalid-pdf" else workflow.pdf_bytes
    response = service.client.post(
        "/api/capture",
        headers=service.headers,
        data={"trade_type": "iamLoan"},
        files={"pdf": ("contract.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == status
    assert workflow.completion.call_count == model_calls
    assert len(calls) == resolver_calls
    workflow.azure["client"].close.assert_called_once()
    if failure == "unresolved":
        assert response.json()["success"] is False
        assert response.json()["extracted_field_count"] == 0
        assert response.json()["warnings"] == ["missing reference"]
    else:
        assert response.json()["detail"]
