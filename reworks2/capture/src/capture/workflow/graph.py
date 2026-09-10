"""Capture: validate -> extract XML -> resolve references -> shape result.

Node order, duplicate catalog lookup, MCP call and result fields follow the original.
Inputs remain transient; there is no checkpointer or external graph tracing.
"""

from capture.workflow.extract_xml import extract_trade_xml_detail, validate_pdf_bytes
from capture.workflow.prompts import capture_config, get_trade_type_config
from capture.workflow.xml_fields import count_extracted_fields
from langgraph.graph import END, START, StateGraph
from mcp_context import McpCluster
from mcp_rpc import mcp_call_tool_json
from typing import Any, TypedDict
from capture.observability.ai import ai_span, private_graph_run
import asyncio
import logging
import time

log = logging.getLogger("diapason.chat.ic")  # Existing company logger destination.


class CaptureState(TypedDict, total=False):
    pdf_bytes: bytes
    trade_type: str
    view_entity: str
    menu_name: str
    extract: dict[str, Any]
    resolve_body: dict[str, Any]
    extract_ms: int
    resolve_ms: int
    tool_trace: list[dict[str, Any]]
    result: dict[str, Any]


def create_capture_graph(*, cluster: McpCluster, config: dict, azure: dict, debug: bool):
    async def validate(state: CaptureState) -> dict:
        with ai_span("ai.capture.validate"):
            capture = capture_config(config)
            max_pdf = int(capture.get("max_pdf_bytes", 10 * 1024 * 1024) or 10 * 1024 * 1024)
            validate_pdf_bytes(state["pdf_bytes"], max_bytes=max_pdf)
            type_cfg = get_trade_type_config(state["trade_type"])
            view_entity = str(
                type_cfg.get("view_entity") or capture_config(config).get("view_entity") or "loanDeposit"
            ).strip()
            menu_name = str(type_cfg.get("menu_name") or view_entity).strip()
            return {"view_entity": view_entity, "menu_name": menu_name, "tool_trace": []}

    async def extract(state: CaptureState) -> dict:
        with ai_span("ai.capture.extract"):
            started = time.perf_counter()
            detail = await asyncio.to_thread(
                extract_trade_xml_detail, state["pdf_bytes"], state["trade_type"], config, azure
            )
            duration = int((time.perf_counter() - started) * 1000)
            entry = {
                # These labels are serialized to the existing UI/session contract.
                "name": "intelligence-contract", "tool": "extract_xml",
                "mcp_label": "Intelligence contract", "duration_ms": duration,
                "arguments": {"trade_type": state["trade_type"], "prompt_blob": detail.get("prompt_blob")},
            }
            return {"extract": detail, "extract_ms": duration, "tool_trace": [entry]}

    async def resolve(state: CaptureState) -> dict:
        with ai_span("ai.capture.tool"):
            started = time.perf_counter()
            body = mcp_call_tool_json(
                cluster.diapason, "resolveReferences",
                {"view_entity": state["view_entity"], "trade_xml": state["extract"]["trade_xml"]},
                timeout_s=180.0,
            )
            duration = int((time.perf_counter() - started) * 1000)
            entry = {
                "name": "resolveReferences", "tool": "resolveReferences",
                "mcp_server": cluster.diapason.server_id if cluster.diapason else "default",
                "mcp_label": cluster.diapason.label if cluster.diapason else "Diapason",
                "duration_ms": duration, "arguments": {
                    "view_entity": state["view_entity"], "menu_name": state["menu_name"],
                    "trade_type": state["trade_type"],
                },
            }
            return {"resolve_body": body, "resolve_ms": duration,
                    "tool_trace": state["tool_trace"] + [entry]}

    async def shape_result(state: CaptureState) -> dict:
        body, detail = state["resolve_body"], state["extract"]
        success = bool(body.get("success"))
        resolved_xml = str(body.get("trade_xml") or "").strip()
        message = str(body.get("message") or "")
        warnings = []
        resolve_warnings = body.get("warnings")
        if isinstance(resolve_warnings, list):
            warnings.extend(str(w) for w in resolve_warnings if w)
        if success and not resolved_xml:
            success = False
            if not message:
                message = "resolveReferences returned success but no trade_xml"
        if not success:
            # Preserve the result/error contract, but do not export the XML or tool message.
            log.warning("Capture reference resolution failed")
        result = {
            "success": success, "trade_xml": resolved_xml, "view_entity": state["view_entity"],
            "menu_name": state["menu_name"], "trade_type": state["trade_type"],
            "extracted_field_count": count_extracted_fields(resolved_xml) if success else 0,
            "message": message, "warnings": warnings, "tool_trace": state["tool_trace"],
            "session_artifacts": {
                "extract": detail, "resolve_references": body,
                "source_trade_xml": detail["trade_xml"], "resolved_trade_xml": resolved_xml,
            },
            "timings_ms": {"extract": state["extract_ms"], "resolve": state["resolve_ms"]},
        }
        if debug:
            result["debug"] = {
                "extract": detail, "resolve_references": body,
                "resolve_references_request": {
                    "view_entity": state["view_entity"], "trade_xml": detail["trade_xml"],
                },
            }
        return {"result": result}

    graph = StateGraph(CaptureState)
    graph.add_node("validate", validate)
    graph.add_node("extract", extract)
    graph.add_node("resolve", resolve)
    graph.add_node("result", shape_result)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "extract")
    graph.add_edge("extract", "resolve")
    graph.add_edge("resolve", "result")
    graph.add_edge("result", END)
    return graph.compile()


async def run_capture(
    *, pdf_bytes: bytes, trade_type: str, cluster: McpCluster,
    config: dict[str, Any], azure: dict[str, Any], debug: bool = False,
) -> dict[str, Any]:
    with private_graph_run(), ai_span("ai.capture.workflow") as span:
        graph = create_capture_graph(cluster=cluster, config=config, azure=azure, debug=debug)
        final = await graph.ainvoke(
            {"pdf_bytes": pdf_bytes, "trade_type": trade_type}, config={"callbacks": []}
        )
        if span and not final["result"]["success"]:
            span.set_attribute("ai.result_success", False)
        elif span:
            span.set_attribute("ai.result_success", True)
        return final["result"]
