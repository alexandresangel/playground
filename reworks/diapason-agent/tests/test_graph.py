import asyncio
import json

import pytest
from conftest import FakeMcp, FakeModel, MemoryStore

from pascal.agent.budget import BudgetExceeded, ContextBudget, cost_usd
from pascal.agent.service import BusyError
from pascal.agent.state import ModelReply, ToolCall
from pascal.config import AgentLimits


async def test_real_graph_tool_loop_and_usage(service_factory, identity):
    model = FakeModel(
        [
            ModelReply(
                tool_calls=[ToolCall("one", "balance", '{"account":"A"}')],
                usage={"input": 10, "output": 3, "total": 13},
            ),
            ModelReply(content="100 EUR", usage={"input": 20, "output": 4, "total": 24}),
        ]
    )
    service = service_factory(model=model)
    handle = await service.open(identity=identity, message="Balance?")
    await handle.task
    assert handle.outcome.status == "completed"
    assert handle.outcome.answer == "100 EUR"
    assert handle.outcome.usage["total"] == 37
    assert service.store.writes == 1
    assert model.requests[1][0][-1]["role"] == "tool"
    assert handle.payload({})["chart_spec"] is None
    assert set(service.graph.nodes) == {"__start__", "model", "tools"}


@pytest.mark.parametrize(
    "call",
    [
        ToolCall("a", "missing", "{}"),
        ToolCall("a", "balance", "bad json"),
        ToolCall("a", "balance", '{"account":1}'),
        ToolCall("a", "balance", "[]"),
    ],
)
async def test_invalid_call_never_dispatched(call, service_factory, identity):
    model = FakeModel(
        [ModelReply(tool_calls=[call]), ModelReply(content="Please provide an account.")]
    )
    service = service_factory(model=model)
    handle = await service.open(identity=identity, message="Balance")
    await handle.task
    assert not [request for request in service.transport.requests if request[1] == "tools/call"]
    assert handle.outcome.status == "completed"
    assert json.loads(model.requests[1][0][-1]["content"])["isError"]


async def test_tool_failure_is_recoverable_and_sanitized(service_factory, identity, caplog):
    transport = FakeMcp()
    transport.fail = True
    model = FakeModel(
        [
            ModelReply(tool_calls=[ToolCall("a", "balance", '{"account":"A"}')]),
            ModelReply(content="The balance service is unavailable."),
        ]
    )
    service = service_factory(model=model, transport=transport)
    handle = await service.open(identity=identity, message="Balance")
    await handle.task
    assert handle.outcome.status == "completed"
    assert handle.outcome.traces[0]["error"]
    assert "SECRET_REMOTE_BODY" not in json.dumps(model.requests)
    assert "SECRET_REMOTE_BODY" not in caplog.text
    assert service.store.writes == 1


async def test_disconnect_persists_partial_once(service_factory, identity):
    model = FakeModel([ModelReply(content="Partial")])
    model.block = True
    service = service_factory(model=model)
    handle = await service.open(identity=identity, message="Hello", streaming=True)
    await asyncio.wait_for(model.started.wait(), 5)
    await handle.disconnect()
    assert handle.outcome.status == "cancelled"
    assert handle.outcome.persisted
    assert handle.outcome.answer.startswith("Partial")
    assert service.store.writes == 1
    assert not service.active


async def test_model_failure_and_persistence_failure_reported(service_factory, identity):
    store = MemoryStore()
    store.fail_write = True
    service = service_factory(model=FakeModel([RuntimeError("MODEL SECRET")]), store=store)
    handle = await service.open(identity=identity, message="Hello")
    await handle.task
    assert handle.outcome.status == "persistence_failed"
    assert not handle.outcome.persisted
    assert "MODEL SECRET" not in handle.outcome.answer


async def test_round_limit_final_call_has_no_tools(service_factory, identity):
    model = FakeModel(
        [
            ModelReply(tool_calls=[ToolCall("a", "balance", '{"account":"A"}')]),
            ModelReply(content="Result"),
        ]
    )
    service = service_factory(model=model, limits=AgentLimits(max_tool_rounds=1))
    handle = await service.open(identity=identity, message="Balance")
    await handle.task
    assert model.requests[-1][1] == []
    assert len(model.requests) == 2


async def test_same_session_busy_and_timeout(service_factory, identity):
    model = FakeModel([ModelReply(content="Partial")])
    model.block = True
    service = service_factory(model=model, limits=AgentLimits(turn_timeout_seconds=0.2))
    handle = await service.open(identity=identity, message="Hello")
    await model.started.wait()
    with pytest.raises(BusyError):
        await service.open(identity=identity, message="Again", session_id=handle.session_id)
    await handle.task
    assert handle.outcome.status == "timeout"
    assert handle.outcome.persisted


def test_context_prunes_whole_history_and_truncates_tools():
    budget = ContextBudget(1500, 256)
    messages = [
        {"role": "system", "content": "Policy"},
        {"role": "user", "content": "Old " * 1800},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "Current"},
    ]
    assert budget.fit(messages, []) == [messages[0], messages[-1]]
    text = budget.truncate("Result " * 5000, 128)
    assert budget.count(text) <= 128
    with pytest.raises(BudgetExceeded):
        budget.fit([messages[0], {"role": "user", "content": "huge " * 5000}], [])


def test_cached_cost_and_unknown_prices():
    usage = {"input": 100, "cached_input": 40, "output": 20}
    assert cost_usd(usage, {}) is None
    assert cost_usd(
        usage, {"input_usd_per_1m": 1, "cached_input_usd_per_1m": 0.5, "output_usd_per_1m": 2}
    ) == pytest.approx(0.00012)


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef", "$recursiveRef"])
async def test_external_schema_references_never_dispatch(keyword, service_factory, identity):
    transport = FakeMcp(
        rows=[
            {
                "name": "balance",
                "inputSchema": {
                    "type": "object",
                    "properties": {"account": {keyword: "https://private.example/schema"}},
                },
            }
        ]
    )
    model = FakeModel(
        [
            ModelReply(tool_calls=[ToolCall("one", "balance", '{"account":"A"}')]),
            ModelReply(content="This tool schema is unsupported."),
        ]
    )
    service = service_factory(model=model, transport=transport)
    handle = await service.open(identity=identity, message="Balance")
    await handle.task
    assert not [request for request in transport.requests if request[1] == "tools/call"]
    assert handle.outcome.traces[0]["error"]
