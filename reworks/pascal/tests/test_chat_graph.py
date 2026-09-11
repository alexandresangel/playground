import ast
import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from pascal.agent import graph, service
from pascal.agent.discovery import _filter_tool_definitions
from pascal.agent.mcp import _parse_tool_arguments
from source_extract import extract_sources_from_tool_result, merge_source_lists
from telemetry import merge_usage, usage_from_completion


class Stream:
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    def __iter__(self):
        yield from self.chunks

    def close(self):
        self.closed = True


def chunk(content=None, calls=None, usage=None):
    return NS(choices=[NS(delta=NS(content=content, tool_calls=calls))], usage=usage)


class Model:
    def __init__(self, tool_rounds=1, content="answer"):
        self.chat = NS(completions=NS(create=self.create))
        self.calls = []
        self.streams = []
        self.closed = False
        self.tool_rounds, self.content = tool_rounds, content

    def close(self):
        self.closed = True

    def create(self, **kwargs):
        turn = len(self.calls)
        self.calls.append(copy.deepcopy(kwargs))
        usage = NS(prompt_tokens=10, completion_tokens=3, total_tokens=13)
        tools = turn < self.tool_rounds
        if not kwargs.get("stream"):
            calls = [NS(id=f"call-{turn}", function=NS(name="balance", arguments='{"scope": 3}'))] if tools else []
            return NS(choices=[NS(message=NS(content=None if tools else self.content, tool_calls=calls))], usage=usage)
        if tools:
            chunks = [
                chunk(calls=[NS(index=0, id=f"call-{turn}", function=NS(name="bal", arguments='{"scope":'))]),
                chunk(calls=[NS(index=0, id=None, function=NS(name="ance", arguments=' 3}'))]),
            ]
        else:
            chunks = [chunk(content=self.content[:2]), chunk(content=self.content[2:])]
        chunks.append(NS(choices=[], usage=usage))
        stream = Stream(chunks)
        self.streams.append(stream)
        return stream


def tool(name, args):
    return {"value": "résultat"}, {"name": name, "tool": name, "arguments": args, "duration_ms": 5, "mcp_server": "default", "mcp_label": "Diapason"}


def dependencies(client, rounds=4, allowed=None):
    return dict(client=client, deployment="same-deployment", tools=[], max_rounds=rounds, locale="en_us", allowed_tool_names=allowed, invoke_tool=tool, parse_arguments=_parse_tool_arguments)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("rounds,tool_rounds,expected_calls,exhausted", [(4, 0, 1, False), (4, 2, 3, False), (0, 1, 1, True), (1, 3, 2, True), (12, 12, 13, False), (-1, 1, 0, True)])
def test_round_limits_usage_and_model_parameters(streaming, rounds, tool_rounds, expected_calls, exhausted):
    client = Model(tool_rounds)
    messages = [{"role": "system", "content": "original prompt"}, {"role": "user", "content": "hello"}]
    if streaming:
        events = list(graph.stream_chat(messages, **dependencies(client, rounds)))
        result = events[-1]["result"]
        assert all(stream.closed for stream in client.streams)
    else:
        result = graph.run_chat(messages, **dependencies(client, rounds))
    assert len(client.calls) == expected_calls
    assert result["answer"] == (graph.ROUND_LIMIT_MESSAGE if exhausted else "answer")
    assert result["usage"] == ({"input": expected_calls * 10, "output": expected_calls * 3, "total": expected_calls * 13} if expected_calls else {})
    assert len(result["tool_trace"]) == min(expected_calls, tool_rounds)
    for call in client.calls:
        assert call["model"] == "same-deployment" and call["temperature"] == 0.2
        assert call["tools"] is None and call["tool_choice"] is None
        assert call["messages"][0]["content"] == "original prompt"


@pytest.mark.parametrize("streaming", [False, True])
def test_routed_tool_allowlist_enforced(streaming):
    client = Model()
    invoke = Mock()
    deps = {**dependencies(client, allowed=["different"]), "invoke_tool": invoke}
    with pytest.raises(RuntimeError, match="not allowed"):
        if streaming: list(graph.stream_chat([], **deps))
        else: graph.run_chat([], **deps)
    invoke.assert_not_called()


def test_stream_retry_without_usage_options_and_cleanup():
    stream = Stream([chunk(content="ok")])
    create = Mock(side_effect=[RuntimeError("old API rejects stream_options"), stream])
    events = []
    result = graph._stream_model(NS(chat=NS(completions=NS(create=create))), {"model": "same"}, events.append)
    assert result == ("ok", [], {}) and stream.closed
    assert "stream_options" in create.call_args_list[0].kwargs
    assert "stream_options" not in create.call_args_list[1].kwargs


def test_delta_arrives_before_model_stream_completes():
    released = threading.Event()
    def chunks():
        yield chunk(content="first")
        assert released.wait(5), "Graph buffered the first delta until model completion"
        yield chunk(content="second")
    stream = Stream(chunks())
    model = NS(chat=NS(completions=NS(create=lambda **kwargs: stream)))
    events = graph.stream_chat([], **dependencies(model))
    try:
        assert next(events) == {"type": "delta", "content": "first"}
        released.set()
        assert [event["type"] for event in events] == ["delta", "workflow_result"]
    finally:
        released.set()
        events.close()
    assert stream.closed


def original_functions(namespace):
    path = Path(__file__).parents[2] / "diapason-agent-main/app.py"
    if not path.is_file():
        pytest.skip("Optional differential check needs the original migration source")
    parsed = ast.parse(path.read_text(encoding="utf-8"))
    names = {"_call_azure_openai_with_mcp_tools", "_iter_chat_stream_events"}
    tree = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    exec(compile(ast.fix_missing_locations(tree), str(path), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("rounds,tool_rounds,content", [(4, 0, "answer"), (4, 2, "answer"), (0, 2, ""), (1, 4, "answer"), (-1, 1, "answer"), (4, 0, "")])
def test_original_loop_differential(monkeypatch, streaming, rounds, tool_rounds, content):
    original_client, migrated_client = Model(tool_rounds, content), Model(tool_rounds, content)
    namespace = original_functions({
        "DEFAULT_LOCALE": "en_us", "json": json, "_CONFIG": {"azure_openai": {"max_tool_rounds": rounds}},
        "_build_azure_client": lambda: {"client": original_client, "deployment": "same-deployment"},
        "_get_mcp_tool_definitions": lambda cluster: [], "_filter_tool_definitions": _filter_tool_definitions,
        "_parse_tool_arguments": _parse_tool_arguments, "_invoke_mcp_tool": lambda cluster, name, args: tool(name, args),
        "merge_usage": merge_usage, "usage_from_completion": usage_from_completion,
        "merge_source_lists": merge_source_lists, "extract_sources_from_tool_result": extract_sources_from_tool_result,
        "_looks_like_chart_request": lambda message: False,
    })
    runtime = NS(config=namespace["_CONFIG"], azure_client=lambda: {"client": migrated_client, "deployment": "same-deployment"})
    monkeypatch.setattr(service, "_get_mcp_tool_definitions", lambda *args: [])
    monkeypatch.setattr(service, "_invoke_mcp_tool", lambda runtime, cluster, name, args: tool(name, args))
    old_messages = [{"role": "user", "content": "hello"}]
    new_messages = copy.deepcopy(old_messages)
    if streaming:
        expected = list(namespace["_iter_chat_stream_events"](old_messages, "hello", "sid", "mcp", None))
        actual = list(service._iter_chat_stream_events(runtime, new_messages, "hello", "sid", "mcp", None))
    else:
        expected = namespace["_call_azure_openai_with_mcp_tools"](old_messages, None)
        actual = service._call_azure_openai_with_mcp_tools(runtime, new_messages, None)
    assert actual == expected
    assert migrated_client.calls == original_client.calls
    assert new_messages == old_messages
    assert migrated_client.closed
