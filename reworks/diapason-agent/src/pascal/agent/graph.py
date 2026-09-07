"""The single agent loop used by both HTTP response modes."""

import asyncio
import json
import time
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from pascal.agent.budget import BudgetExceeded, ContextBudget, cost_usd
from pascal.agent.state import PascalState, TurnOutcome
from pascal.config import AgentLimits
from pascal.observability.events import operation, safe_arguments
from pascal.ports import McpTransport, Model
from pascal.tools.registry import BoundTool
from pascal.tools.sources import extract_sources_from_tool_result, merge_source_lists


@dataclass
class GraphContext:
    model: Model
    transport: McpTransport
    tools: list[BoundTool]
    limits: AgentLimits
    budget: ContextBudget
    rates: dict
    outcome: TurnOutcome
    locale: str
    started: float


async def model_node(state: PascalState, runtime: Runtime[GraphContext]) -> dict:
    ctx = runtime.context
    outcome, writer = ctx.outcome, get_stream_writer()
    # A final synthesis call cannot start another tool round.
    allow_tools = (
        state["rounds"] < ctx.limits.max_tool_rounds
        and state["tool_count"] < ctx.limits.max_tool_calls
    )
    definitions = [tool.definition for tool in ctx.tools] if allow_tools else []
    messages = ctx.budget.fit(state["messages"], definitions)
    if ctx.limits.max_usd_per_turn is not None:
        next_cost = (
            cost_usd(
                {
                    "input": ctx.budget.count({"messages": messages, "tools": definitions}),
                    "output": ctx.limits.max_output_tokens,
                },
                ctx.rates,
            )
            or 0
        )
        if (cost_usd(outcome.usage, ctx.rates) or 0) + next_cost > ctx.limits.max_usd_per_turn:
            raise BudgetExceeded("cost_limit")

    async def delta(content: str):
        outcome.answer += content
        if outcome.first_token_ms is None:
            outcome.first_token_ms = int((time.monotonic() - ctx.started) * 1000)
        writer({"type": "delta", "content": content})

    with operation("chat.model") as span:
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.provider.name", "azure.ai.openai")
        span.set_attribute("chat.round", state["rounds"])
        async with asyncio.timeout(
            ctx.limits.model_timeout_seconds * (ctx.limits.model_retries + 1)
        ):
            reply = await ctx.model.complete(
                messages, definitions, ctx.limits.max_output_tokens, delta
            )
        if not reply.usage:
            # Conservative local estimate when Azure omits usage; clearly labelled downstream.
            reply.usage = {
                "input": ctx.budget.count({"messages": messages, "tools": definitions}),
                "output": ctx.budget.count(reply.content)
                + sum(ctx.budget.count(c.arguments) for c in reply.tool_calls),
                "estimated": 1,
            }
            reply.usage["total"] = reply.usage["input"] + reply.usage["output"]
        for key, value in reply.usage.items():
            outcome.usage[key] = outcome.usage.get(key, 0) + value
        span.set_attribute("gen_ai.usage.input_tokens", reply.usage.get("input", 0))
        span.set_attribute("gen_ai.usage.output_tokens", reply.usage.get("output", 0))
    outcome.rounds += 1
    if reply.finish_reason == "length":
        raise BudgetExceeded("model_output_limit")
    if reply.finish_reason == "content_filter":
        raise RuntimeError("model_content_filtered")
    message = {"role": "assistant", "content": reply.content or None}
    if reply.tool_calls and allow_tools:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                },
            }
            for call in reply.tool_calls
        ]
    if reply.tool_calls and not allow_tools:
        raise BudgetExceeded("tool_round_limit")
    return {
        "messages": [*messages, message],
        "pending": reply.tool_calls,
        "stop": not bool(reply.tool_calls),
    }


async def tools_node(state: PascalState, runtime: Runtime[GraphContext]) -> dict:
    ctx, writer = runtime.context, get_stream_writer()
    bound = {tool.name: tool for tool in ctx.tools}
    semaphore = asyncio.Semaphore(ctx.limits.max_parallel_tools)

    async def invoke(index, call):
        started = time.monotonic()
        tool = bound.get(call.name)
        args, error, result = {}, None, {}
        entry = dict(
            name=call.name,
            tool=tool.info["native_name"] if tool else call.name,
            mcp_server=tool.server.server_id if tool else "unknown",
            mcp_label=tool.server.label if tool else "unknown",
            arguments={},
            duration_ms=0,
        )
        ctx.outcome.traces.append(entry)
        try:
            if state["tool_count"] + index >= ctx.limits.max_tool_calls:
                raise ValueError("tool_call_limit")
            if tool is None:
                raise ValueError("unknown_or_disallowed_tool")
            if len(call.arguments) > ctx.limits.max_tool_argument_chars:
                raise ValueError("tool_arguments_too_large")
            args = json.loads(call.arguments or "{}")
            entry["arguments"] = safe_arguments(args)
            if not isinstance(args, dict):
                raise ValueError("invalid_tool_arguments")
            schema = tool.info["input_schema"]
            # External references are not resolved; never fetch schema URLs.
            if '"$ref"' in json.dumps(schema):

                def external_ref(node):
                    if isinstance(node, dict):
                        if "$ref" in node and not str(node["$ref"]).startswith("#"):
                            return True
                        return any(external_ref(v) for v in node.values())
                    return isinstance(node, list) and any(external_ref(v) for v in node)

                if external_ref(schema):
                    raise ValueError("unsupported_tool_schema")
            Draft202012Validator(schema).validate(args)
            writer({"type": "status", "content": f"Calling {call.name}…"})
            with operation("chat.tool") as span:
                span.set_attribute("gen_ai.tool.name", tool.name)
                span.set_attribute("mcp.server", tool.server.server_id)
                async with semaphore:
                    result = await ctx.transport.request(
                        tool.server,
                        "tools/call",
                        {
                            "name": tool.info["native_name"],
                            "arguments": args,
                        },
                    )
                if result.get("isError"):
                    error = "tool_reported_error"
                span.set_attribute("tool.ok", error is None)
        except asyncio.CancelledError:
            entry["error"] = "tool_interrupted_result_unknown"
            raise
        except Exception:
            error = "tool_unavailable_or_invalid_arguments"
        finally:
            entry["duration_ms"] = int((time.monotonic() - started) * 1000)
        if error:
            entry["error"] = error
            result = {
                "isError": True,
                "error": error,
                "instruction": "Explain the limitation or fix the arguments. Never invent results.",
            }
        sources = extract_sources_from_tool_result(result, entry, locale=ctx.locale)
        ctx.outcome.sources = merge_source_lists(ctx.outcome.sources, sources, locale=ctx.locale)
        writer({"type": "tool", **entry})
        return (
            entry,
            sources,
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": ctx.budget.truncate(result, ctx.limits.max_tool_result_tokens),
            },
        )

    pending = state["pending"]
    # readOnlyHint is an optimization hint, not authorization. Unannotated/mutating calls
    # retain ordering and are never automatically retried.
    if all(call.name in bound and bound[call.name].readonly for call in pending):
        results = await asyncio.gather(*(invoke(i, call) for i, call in enumerate(pending)))
    else:
        results = [await invoke(i, call) for i, call in enumerate(pending)]
    if ctx.outcome.sources:
        writer({"type": "sources", "items": ctx.outcome.sources})
    return {
        "messages": [*state["messages"], *(message for _, _, message in results)],
        "rounds": state["rounds"] + 1,
        "tool_count": state["tool_count"] + len(pending),
        "pending": [],
    }


def build_graph():
    graph = StateGraph(PascalState, context_schema=GraphContext)
    graph.add_node("model", model_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "model")
    graph.add_conditional_edges(
        "model", lambda state: "done" if state["stop"] else "tools", {"done": END, "tools": "tools"}
    )
    graph.add_edge("tools", "model")
    return graph.compile()
