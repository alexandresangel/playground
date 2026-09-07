import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from conftest import FakeMcp, FakeModel

from pascal.agent.service import BusyError
from pascal.agent.state import ExternalResult, ModelReply, ToolCall
from pascal.config import AgentLimits, limits_from_config


async def test_interrupted_tool_attempt_retained(service_factory, identity):
    entered = asyncio.Event()

    class BlockingMcp(FakeMcp):
        async def request(self, server, method, params):
            if method == "tools/call":
                entered.set()
                await asyncio.Event().wait()
            return await super().request(server, method, params)

    model = FakeModel([ModelReply(tool_calls=[ToolCall("one", "balance", '{"account":"A"}')])])
    service = service_factory(model=model, transport=BlockingMcp())
    handle = await service.open(identity=identity, message="Balance")
    await entered.wait()
    await handle.disconnect()
    assert handle.outcome.traces[0]["error"] == "tool_interrupted_result_unknown"
    assert handle.outcome.persisted
    assert service.store.writes == 1
    record = service.store.get_session(handle.session_id, identity.scope_path)
    assert record["turns"][-1]["tool_trace"][0]["error"] == "tool_interrupted_result_unknown"


async def test_external_capture_shares_admission_and_cancel_persistence(service_factory, identity):
    entered = asyncio.Event()

    async def capture(sid):
        entered.set()
        await asyncio.Event().wait()
        return ExternalResult({}, "never reached", {})

    service = service_factory()
    handle = await service.open(identity=identity, message="Capture intent", external=capture)
    await entered.wait()
    with pytest.raises(BusyError):
        await service.open(identity=identity, message="same session", session_id=handle.session_id)
    await handle.disconnect()
    assert service.store.writes == 1
    assert handle.outcome.status == "cancelled"
    assert not service.model.requests


def test_live_evaluation_grader_is_not_a_quality_oracle(monkeypatch):
    scripts = Path(__file__).parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("pascal_evaluation", scripts / "evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = {"id": "case", "must_contain": ["verified"], "required_tools": ["balance"]}
    result = module.grade(
        case,
        {
            "status": "completed",
            "persisted": True,
            "answer_markdown": "unrelated",
            "tool_trace": [],
        },
    )
    assert not result["passed"]
    assert result["human_review"] == "required"
    starter = json.loads(
        (scripts.parent / "evaluation/cases.example.json").read_text(encoding="utf-8")
    )
    assert len(starter["cases"]) == 10
    assert not starter["approved_by"]


async def test_ambient_langsmith_tracing_cannot_export_turn(service_factory, identity, monkeypatch):
    from langsmith import Client

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-not-real")
    calls = []

    def forbidden_export(*args, **kwargs):
        calls.append(1)
        raise AssertionError("Content tracing must remain disabled")

    monkeypatch.setattr(Client, "create_run", forbidden_export)
    service = service_factory()
    handle = await service.open(identity=identity, message="Private")
    await handle.task
    assert handle.outcome.status == "completed"
    assert not calls


async def test_output_limit_is_not_reported_as_complete(service_factory, identity):
    service = service_factory(
        model=FakeModel([ModelReply(content="Cut off", finish_reason="length")])
    )
    handle = await service.open(identity=identity, message="Long answer")
    await handle.task
    assert handle.outcome.status == "limit_reached"
    assert handle.outcome.persisted


async def test_global_admission_limit(service_factory, identity):
    model = FakeModel([ModelReply(content="Partial")])
    model.block = True
    service = service_factory(model=model, limits=AgentLimits(max_active_turns=1))
    handle = await service.open(identity=identity, message="First")
    try:
        with pytest.raises(BusyError):
            await service.open(identity=identity, message="Second")
    finally:
        await handle.disconnect()


async def test_message_and_argument_limits(service_factory, identity):
    service = service_factory(limits=AgentLimits(max_message_chars=3))
    with pytest.raises(ValueError):
        await service.open(identity=identity, message="four")
    model = FakeModel(
        [
            ModelReply(tool_calls=[ToolCall("a", "balance", json.dumps({"account": "A" * 1100}))]),
            ModelReply(content="Input too large"),
        ]
    )
    service = service_factory(model=model, limits=AgentLimits(max_tool_argument_chars=1024))
    handle = await service.open(identity=identity, message="Balance")
    await handle.task
    assert not [r for r in service.transport.requests if r[1] == "tools/call"]


async def test_individual_model_timeout(service_factory, identity):
    model = FakeModel([ModelReply(content="Partial")])
    model.block = True
    service = service_factory(
        model=model, limits=AgentLimits(model_timeout_seconds=0.01, model_retries=0)
    )
    handle = await service.open(identity=identity, message="Hello")
    await handle.task
    assert handle.outcome.status == "timeout"
    assert handle.outcome.persisted


@pytest.mark.parametrize("rate", [float("nan"), float("inf"), -1])
def test_nonfinite_or_negative_prices_fail_at_configuration(rate):
    with pytest.raises(ValueError):
        limits_from_config({"azure_openai": {"input_usd_per_1m": rate}})


async def test_external_schema_reference_never_fetched_or_dispatched(service_factory, identity):
    mcp = FakeMcp(rows=[{"name": "balance", "inputSchema": {"$ref": "https://private/schema"}}])
    model = FakeModel(
        [ModelReply(tool_calls=[ToolCall("a", "balance", "{}")]), ModelReply(content="Unavailable")]
    )
    service = service_factory(model=model, transport=mcp)
    handle = await service.open(identity=identity, message="Balance")
    await handle.task
    assert not [r for r in mcp.requests if r[1] == "tools/call"]


def test_prompt_refresh_failure_keeps_snapshot(service_factory, monkeypatch):
    provider = service_factory().prompts
    old = provider.snapshot

    def fail():
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(provider, "fetch", fail)
    with pytest.raises(RuntimeError):
        provider.refresh()
    assert provider.snapshot == old
    one, v1 = provider.compose([], "one", "en_us", "UTC")
    two, v2 = provider.compose([], "two", "fr_fr", "Europe/Paris")
    assert one[0] == two[0]
    assert v1 == v2
