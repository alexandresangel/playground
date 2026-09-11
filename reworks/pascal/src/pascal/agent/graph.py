from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from typing import Any, Callable, TypedDict
import json

from source_extract import extract_sources_from_tool_result, merge_source_lists
from telemetry import merge_usage, usage_from_completion
from pascal.observability.ai import ai_span, private_graph_run, record_usage

ROUND_LIMIT_MESSAGE = "Tool-calling stopped after reaching max rounds."


class ChatState(TypedDict):
    messages: list[dict[str, Any]]
    round_count: int
    content: str
    tool_calls: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    sources: list[dict[str, str]]
    usage: dict[str, Any]
    result: dict[str, Any]


def create_chat_graph(
    *, client, deployment: str, tools: list[dict], allowed_tool_names: list[str] | None,
    max_rounds: int, locale: str, streaming: bool,
    invoke_tool: Callable, parse_arguments: Callable,
):
    """Use the original limits: max_rounds + 1 model calls, including final tools."""
    allowed = {name for name in (allowed_tool_names or []) if isinstance(name, str)}

    def model(state: ChatState) -> dict:
        kwargs = dict(
            model=deployment, messages=state["messages"],
            tools=tools if tools else None, tool_choice="auto" if tools else None,
            temperature=0.2,
        )
        with ai_span("ai.pascal.model") as span:
            if streaming:
                content, calls, usage = _stream_model(client, kwargs, get_stream_writer())
            else:
                response = client.chat.completions.create(**kwargs)
                usage = usage_from_completion(response)
                message = response.choices[0].message
                content = message.content or ""
                calls = [
                    {"id": tc.id, "type": "function", "function": {
                        "name": tc.function.name, "arguments": tc.function.arguments,
                    }} for tc in (message.tool_calls or [])
                ]
            record_usage(span, usage)
        return {
            "round_count": state["round_count"] + 1, "content": content,
            "tool_calls": calls, "usage": merge_usage(state["usage"], usage),
        }

    def call_tools(state: ChatState) -> dict:
        messages = state["messages"]
        calls = state["tool_calls"]
        writer = get_stream_writer()
        if streaming:
            for call in calls:
                name = call["function"]["name"] or "tool"
                writer({"type": "status", "content": f"Calling {name}…"})
        messages.append({
            "role": "assistant",
            "content": (state["content"] or None) if streaming else state["content"],
            "tool_calls": calls,
        })
        trace, sources = list(state["tool_trace"]), list(state["sources"])
        for call in calls:
            name = call["function"]["name"]
            arguments = parse_arguments(call["function"]["arguments"] or "{}")
            if allowed and name not in allowed:
                raise RuntimeError(f"Tool {name!r} is not allowed for this routed request")
            with ai_span("ai.pascal.tool"):
                result, entry = invoke_tool(name, arguments)
            trace.append(entry)
            new_sources = extract_sources_from_tool_result(result, entry, locale=locale)
            if not streaming or new_sources:
                before = len(sources)
                sources = merge_source_lists(sources, new_sources, locale=locale)
                if streaming and sources[before:]:
                    writer({"type": "sources", "items": sources[before:]})
            if streaming:
                writer({
                    "type": "tool", "name": entry["name"], "tool": entry.get("tool"),
                    "mcp_server": entry.get("mcp_server"), "mcp_label": entry.get("mcp_label"),
                    "arguments": arguments, "duration_ms": entry["duration_ms"],
                })
            messages.append({
                "role": "tool", "tool_call_id": call["id"],
                "content": json.dumps(result, ensure_ascii=True),
            })
        return {"messages": messages, "tool_trace": trace, "sources": sources}

    def finish(state: ChatState) -> dict:
        exhausted = bool(state["tool_calls"]) or state["round_count"] == 0
        answer = ROUND_LIMIT_MESSAGE if exhausted else (
            state["content"] or ("" if streaming else "No content returned by the model.")
        )
        result = {"answer": answer, "tool_trace": state["tool_trace"],
                  "sources": state["sources"], "usage": state["usage"]}
        if streaming:
            writer = get_stream_writer()
            if exhausted:
                writer({"type": "delta", "content": answer})
            writer({"type": "workflow_result", "result": result})
        return {"result": result}

    graph = StateGraph(ChatState)
    graph.add_node("model", model)
    graph.add_node("tools", call_tools)
    graph.add_node("finish", finish)
    graph.add_edge(START, "model" if max_rounds >= 0 else "finish")
    graph.add_conditional_edges("model", lambda state: "tools" if state["tool_calls"] else "finish")
    graph.add_conditional_edges(
        "tools", lambda state: "model" if state["round_count"] <= max_rounds else "finish"
    )
    graph.add_edge("finish", END)
    return graph.compile()


def _stream_model(client, kwargs: dict, writer: Callable) -> tuple[str, list[dict], dict]:
    kwargs.update(stream=True, stream_options={"include_usage": True})
    try:
        stream = client.chat.completions.create(**kwargs)
    except Exception:
        # Original broad retry is preserved; narrowing it is a separate behavior change.
        kwargs.pop("stream_options", None)
        stream = client.chat.completions.create(**kwargs)
    by_index: dict[int, dict[str, str]] = {}
    content: list[str] = []
    usage: dict = {}
    try:
        for chunk in stream:
            chunk_usage = usage_from_completion(chunk)
            if chunk_usage:
                usage = merge_usage(usage, chunk_usage)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content.append(delta.content)
                writer({"type": "delta", "content": delta.content})
            for tc in (delta.tool_calls or []):
                idx = tc.index if tc.index is not None else 0
                acc = by_index.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    acc["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        acc["name"] += tc.function.name
                    if tc.function.arguments:
                        acc["arguments"] += tc.function.arguments
    finally:
        stream.close()
    calls = [{"id": by_index[idx]["id"], "type": "function", "function": {
        "name": by_index[idx]["name"], "arguments": by_index[idx]["arguments"],
    }} for idx in sorted(by_index)]
    return "".join(content), calls, usage


def initial_state(messages: list[dict]) -> ChatState:
    return {"messages": messages, "round_count": 0, "content": "", "tool_calls": [],
            "tool_trace": [], "sources": [], "usage": {}, "result": {}}


def run_chat(messages: list[dict], **dependencies) -> dict:
    with private_graph_run(), ai_span("ai.pascal.workflow") as span:
        graph = create_chat_graph(streaming=False, **dependencies)
        result = graph.invoke(initial_state(messages), config={
            "callbacks": [], "recursion_limit": max(4, 2 * (dependencies["max_rounds"] + 1) + 2),
        })["result"]
        record_usage(span, result["usage"])
        return result


def stream_chat(messages: list[dict], **dependencies):
    with private_graph_run(), ai_span("ai.pascal.workflow") as span:
        graph = create_chat_graph(streaming=True, **dependencies)
        for event in graph.stream(initial_state(messages), stream_mode="custom", config={
            "callbacks": [], "recursion_limit": max(4, 2 * (dependencies["max_rounds"] + 1) + 2),
        }):
            if event["type"] == "workflow_result":
                record_usage(span, event["result"]["usage"])
            yield event