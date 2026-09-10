"""Offline Pascal characterization, including the original loop when available."""

import ast
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from pascal.agent.graph import run_chat, stream_chat
from pascal.agent import context, service
from source_extract import extract_sources_from_tool_result, merge_source_lists
from telemetry import merge_usage, usage_from_completion


class Stream:
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    def __iter__(self):
        return iter(self.chunks)

    def close(self):
        self.closed = True


def chunk(content=None, calls=None, usage=None):
    return NS(choices=[NS(delta=NS(content=content, tool_calls=calls))], usage=usage)


def completion(content="answer", calls=None):
    return NS(choices=[NS(message=NS(content=content, tool_calls=calls))],
              usage=NS(prompt_tokens=10, completion_tokens=2, total_tokens=12))


def tool(name="docs__ask_docs", args='{"query":"question"}', call_id="call-1"):
    return NS(id=call_id, function=NS(name=name, arguments=args))


def responses(streaming, scenario):
    calls = [tool()]
    if scenario == "multiple":
        calls += [tool(args='{"query":"second"}', call_id="call-2")]
    if scenario == "malformed":
        calls = [tool(args="[not-json")]
    if scenario == "disallowed":
        calls = [tool(name="forbidden")]
    if scenario in ("empty", "plain"):
        calls = []
    if not streaming:
        return [completion("" if scenario == "empty" else "first", calls), completion("final")]
    if scenario == "empty":
        return [Stream([NS(choices=[], usage=None)])]
    fragments = []
    for idx, call in enumerate(calls):
        name, args = call.function.name, call.function.arguments
        fragments.append(NS(index=idx, id=call.id, function=NS(name=name[:4], arguments=args[:5])))
        fragments.append(NS(index=idx, id=None, function=NS(name=name[4:], arguments=args[5:])))
    return [Stream([chunk("first"), chunk(calls=fragments), NS(choices=[], usage=NS(prompt_tokens=10, completion_tokens=2, total_tokens=12))]),
            Stream([chunk("fin"), chunk("al"), NS(choices=[], usage=NS(prompt_tokens=20, completion_tokens=3, total_tokens=23))])]


def execute(offline, streaming, scenario, max_rounds, original=False):
    namespace = vars(service) if not original else dict(vars(service))
    if original:
        namespace.update(json=json, merge_usage=merge_usage, usage_from_completion=usage_from_completion,
                         extract_sources_from_tool_result=extract_sources_from_tool_result,
                         merge_source_lists=merge_source_lists)
        original_file = Path(__file__).resolve().parents[3] / "app.py"
        if not original_file.is_file():
            pytest.skip("Original repository absent; standalone graph/HTTP tests still run")
        tree = ast.parse(original_file.read_text(encoding="utf-8"))
        wanted = {"_call_azure_openai_with_mcp_tools", "_iter_chat_stream_events"}
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted], type_ignores=[]), str(original_file), "exec"), namespace)
    model = MagicMock()
    outputs = responses(streaming, scenario)
    model_calls, tool_calls, discoveries = [], [], []

    def create(**kwargs):
        model_calls.append(deepcopy(kwargs))
        return outputs.pop(0)

    model.chat.completions.create.side_effect = create
    cluster = object()

    def invoke(received_cluster, name, arguments):
        assert received_cluster is cluster
        tool_calls.append((name, arguments))
        if scenario == "tool_error":
            raise RuntimeError("same tool failure")
        return {"sources": [{"url": "https://doc.test/doc-internal/en_us/page", "title": "Citation"}]}, {
            "name": name, "tool": "ask_docs", "mcp_server": "docs", "mcp_label": "Docs", "duration_ms": 7,
            "arguments": arguments,
        }

    def discover(received_cluster):
        assert received_cluster is cluster
        discoveries.append(received_cluster)
        return [{"type": "function", "function": {"name": "docs__ask_docs", "parameters": {"type": "object"}}}]

    patcher = pytest.MonkeyPatch()
    azure_client = lambda: {"client": model, "deployment": "same-deployment"}
    config = {"azure_openai": {"max_tool_rounds": max_rounds}}
    if original:
        patcher.setitem(namespace, "_build_azure_client", azure_client)
        patcher.setitem(namespace, "_CONFIG", config)
        patcher.setitem(namespace, "_get_mcp_tool_definitions", discover)
        patcher.setitem(namespace, "_invoke_mcp_tool", invoke)
    else:
        patcher.setattr(offline.runtime, "azure_client", azure_client)
        patcher.setattr(offline.runtime, "config", config)
        patcher.setitem(namespace, "_get_mcp_tool_definitions", lambda runtime, cluster: discover(cluster))
        patcher.setitem(namespace, "_invoke_mcp_tool", lambda runtime, *args: invoke(*args))
    runtime_args = [] if original else [offline.runtime]
    messages = [{"role": "system", "content": "unchanged prompt"}, {"role": "user", "content": "question"}]
    try:
        if streaming:
            result = list(namespace["_iter_chat_stream_events"](*runtime_args, messages, "question", "session", "summary", cluster, allowed_tool_names=["docs__ask_docs"]))
        else:
            result = namespace["_call_azure_openai_with_mcp_tools"](*runtime_args, messages, cluster, ["docs__ask_docs"])
    except Exception as exc:
        result = (type(exc).__name__, str(exc))
    finally:
        patcher.undo()
    return result, messages, model_calls, tool_calls, len(discoveries)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("scenario,max_rounds", [("plain", 4), ("empty", 4), ("tool", 4), ("multiple", 4), ("malformed", 4), ("disallowed", 4), ("tool_error", 4), ("tool", 0), ("tool", -1), ("plain", 30)])
def test_matches_original_loop(offline, streaming, scenario, max_rounds):
    actual = execute(offline, streaming, scenario, max_rounds)
    assert actual == execute(offline, streaming, scenario, max_rounds, original=True)
    # A shared test-harness failure must never look like behavioral parity.
    if max_rounds >= 0:
        assert actual[2], "The model was never exercised"
    if scenario in ("tool_error", "disallowed"):
        assert actual[0][0] == "RuntimeError"
    else:
        assert not isinstance(actual[0], tuple), actual[0]


def test_stream_retry_usage_and_close():
    client = MagicMock()
    output = Stream([chunk("hello"), NS(choices=[], usage=NS(prompt_tokens=12, completion_tokens=4, total_tokens=16))])
    client.chat.completions.create.side_effect = [RuntimeError("unsupported usage option"), output]
    events = list(stream_chat([], client=client, deployment="unchanged", tools=[], allowed_tool_names=None, max_rounds=4,
        locale="en_us", invoke_tool=MagicMock(), parse_arguments=lambda raw: {}))
    assert events[0] == {"type": "delta", "content": "hello"}
    assert events[-1]["result"]["usage"] == {"input": 12, "output": 4, "total": 16}
    assert output.closed
    assert "stream_options" in client.chat.completions.create.call_args_list[0].kwargs
    assert "stream_options" not in client.chat.completions.create.call_args_list[1].kwargs


def test_actual_http_json_sse_persistence_and_headers(offline, headers, monkeypatch):
    app = offline.app
    monkeypatch.setattr(context, "_list_mcp_tools", lambda *a, **k: NS(tools=[]))
    monkeypatch.setattr(context, "_get_mcp_summary", lambda *a: "live summary")
    monkeypatch.setattr(service, "_get_mcp_tool_definitions", lambda *a: [])
    monkeypatch.setattr(context, "get_system_prompt", lambda: "exact prompt")
    model = MagicMock()
    monkeypatch.setattr(offline.runtime, "azure_client", lambda: {"client": model, "deployment": "same"})
    model.chat.completions.create.return_value = completion("answer")
    client = TestClient(app)
    response = client.post("/api/chat", headers=headers, json={"message": "question"})
    assert response.status_code == 200
    assert response.json()["answer_markdown"] == "answer"
    assert set(response.json()) == {"answer_markdown", "session_id", "chart_spec", "chart_reason", "mode", "tool_trace", "sources"}
    sid = response.json()["session_id"]
    assert offline.sessions.appended[-1][1] == "test/7/9"
    assert offline.sessions.appended[-1][4]["usage"]["total"] == 12
    output = Stream([chunk("next"), NS(choices=[], usage=NS(prompt_tokens=5, completion_tokens=1, total_tokens=6))])
    model.chat.completions.create.return_value = output
    response = client.post("/api/chat/stream", headers=headers, json={"message": "follow up", "session_id": sid})
    assert response.status_code == 200
    assert response.headers["X-Diapason-Chat-Session"] == sid
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert response.text.endswith("data: [DONE]\n\n")
    assert '"type": "done"' in response.text and '"type": "delta", "content": "next"' in response.text
    saved = offline.sessions.appended[-1]
    assert saved[2:4] == ("follow up", "next") and saved[4]["usage"]["total"] == 6
    assert output.closed and model.close.call_count == 2
    messages = model.chat.completions.create.call_args.kwargs["messages"]
    assert messages[1:3] == [{"role": "user", "content": "question"}, {"role": "assistant", "content": "answer"}]


def test_missing_azure_fallback_is_preserved(offline, headers, monkeypatch):
    monkeypatch.setattr(context, "_list_mcp_tools", lambda *a, **k: NS(tools=[]))
    monkeypatch.setattr(context, "_get_mcp_summary", lambda *a: "live summary")
    monkeypatch.setattr(context, "get_system_prompt", lambda: "prompt")
    client = TestClient(offline.app)
    response = client.post("/api/chat/stream", headers=headers, json={"message": "hello"})
    assert response.status_code == 200 and "Azure credentials not set" in response.text
    assert '"mode": "mcp-http"' in response.text


def test_configured_round_limit_above_langgraph_default():
    client = MagicMock()
    client.chat.completions.create.return_value = completion("", [tool(name="Balance", args="{}")])
    invoke = MagicMock(return_value=({}, {"name": "Balance"}))
    result = run_chat([], client=client, deployment="same", tools=[], allowed_tool_names=None,
        max_rounds=30, locale="en_us", invoke_tool=invoke, parse_arguments=lambda raw: {})
    assert result["answer"] == "Tool-calling stopped after reaching max rounds."
    assert invoke.call_count == 31 and client.chat.completions.create.call_count == 31


def test_stream_delivers_first_delta_before_model_finishes():
    from threading import Event
    released = Event()

    class LiveStream(Stream):
        def __iter__(self):
            yield chunk("first")
            assert released.wait(3), "Graph buffered the live stream until completion"
            yield chunk("last")

    output = LiveStream([])
    client = MagicMock()
    client.chat.completions.create.return_value = output
    events = stream_chat([], client=client, deployment="same", tools=[], allowed_tool_names=None,
        max_rounds=4, locale="en_us", invoke_tool=MagicMock(), parse_arguments=lambda raw: {})
    try:
        assert next(events) == {"type": "delta", "content": "first"}
        assert not output.closed
    finally:
        released.set()
    remaining = list(events)
    assert remaining[0] == {"type": "delta", "content": "last"}
    assert output.closed


def test_stream_failure_closes_sdk_stream():
    class FailedStream(Stream):
        def __iter__(self):
            yield chunk("partial")
            raise RuntimeError("original failure")

    output = FailedStream([])
    client = MagicMock()
    client.chat.completions.create.return_value = output
    events = stream_chat([], client=client, deployment="same", tools=[], allowed_tool_names=None,
        max_rounds=4, locale="en_us", invoke_tool=MagicMock(), parse_arguments=lambda raw: {})
    with pytest.raises(RuntimeError, match="original failure"):
        list(events)
    assert output.closed


def test_pascal_spans_are_content_free_and_correlated(monkeypatch):
    from pascal.observability import ai as ai_observability
    from langsmith import utils
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    provider, exporter = TracerProvider(), InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(ai_observability, "get_tracer", lambda name: provider.get_tracer(name))
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    client = MagicMock()
    outputs = [completion("private content", [tool(name="Balance", args="{}")]), completion("private answer")]

    def create(**kwargs):
        assert not utils.tracing_is_enabled()
        return outputs.pop(0)

    client.chat.completions.create.side_effect = create
    with provider.get_tracer("company").start_as_current_span("chat.completion") as parent:
        run_chat([{"role": "user", "content": "private prompt"}], client=client, deployment="same", tools=[], allowed_tool_names=None,
            max_rounds=4, locale="en_us", invoke_tool=lambda *a: ({"secret": "private payload"}, {"name": "Balance"}), parse_arguments=lambda raw: {})
    spans = exporter.get_finished_spans()
    assert {s.name for s in spans} >= {"ai.pascal.workflow", "ai.pascal.model", "ai.pascal.tool"}
    assert all(s.context.trace_id == parent.get_span_context().trace_id for s in spans)
    workflow = next(s for s in spans if s.name == "ai.pascal.workflow")
    assert workflow.attributes["gen_ai.usage.total_tokens"] == 24
    assert "private" not in str([(s.attributes, s.events) for s in spans])
    provider.shutdown()
