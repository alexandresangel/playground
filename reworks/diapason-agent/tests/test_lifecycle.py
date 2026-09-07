import asyncio
import threading

import pytest
from conftest import FakeMcp, FakeModel, MemoryStore

from pascal.agent.state import ModelReply, ToolCall
from pascal.config import AgentLimits


async def test_disconnect_before_producer_first_instruction_still_persists(
    service_factory, identity
):
    service = service_factory()
    handle = await service.open(identity=identity, message="Do not lose this intent")
    await handle.disconnect()
    assert handle.outcome.persisted
    assert service.store.writes == 1
    assert not service.model.requests
    assert handle.outcome.status == "cancelled"


async def test_cancel_during_persistence_finishes_one_write(service_factory, identity):
    entered, release = threading.Event(), threading.Event()

    class SlowStore(MemoryStore):
        def append_turn(self, *args, **kwargs):
            entered.set()
            assert release.wait(5)
            return super().append_turn(*args, **kwargs)

    store = SlowStore()
    service = service_factory(store=store)
    handle = await service.open(identity=identity, message="Hello")
    assert await asyncio.to_thread(entered.wait, 5)
    disconnect = asyncio.create_task(handle.disconnect())
    await asyncio.sleep(0)
    release.set()
    await disconnect
    assert store.writes == 1
    assert handle.outcome.persisted
    assert not service.active


async def test_shutdown_cancels_and_persists_active_turn(service_factory, identity):
    model = FakeModel([ModelReply(content="Partial")])
    model.block = True
    service = service_factory(model=model, limits=AgentLimits(shutdown_grace_seconds=0.01))
    handle = await service.open(identity=identity, message="Hello")
    await model.started.wait()
    await service.close()
    assert handle.outcome.persisted
    assert handle.outcome.status == "cancelled"
    assert service.store.writes == 1


async def test_tool_call_limit_blocks_excess_dispatch(service_factory, identity):
    model = FakeModel(
        [
            ModelReply(
                tool_calls=[ToolCall(str(i), "balance", '{"account":"A"}') for i in range(3)]
            ),
            ModelReply(content="Only one call was allowed."),
        ]
    )
    service = service_factory(model=model, limits=AgentLimits(max_tool_calls=1))
    handle = await service.open(identity=identity, message="Balance")
    await handle.task
    assert len([r for r in service.transport.requests if r[1] == "tools/call"]) == 1
    assert len(handle.outcome.traces) == 3
    assert handle.outcome.traces[1]["error"]


@pytest.mark.parametrize("readonly,expected", [(True, 2), (False, 1)])
async def test_parallelism_only_for_explicit_readonly_batch(
    service_factory, identity, readonly, expected
):
    class MeasuredMcp(FakeMcp):
        active, maximum = 0, 0

        async def request(self, server, method, params):
            if method == "tools/call":
                self.active += 1
                self.maximum = max(self.active, self.maximum)
                await asyncio.sleep(0.02)
                self.active -= 1
            return await super().request(server, method, params)

    mcp = MeasuredMcp()
    mcp.rows[0]["annotations"] = {"readOnlyHint": readonly}
    model = FakeModel(
        [
            ModelReply(
                tool_calls=[ToolCall(str(i), "balance", '{"account":"A"}') for i in range(3)]
            ),
            ModelReply(content="Done"),
        ]
    )
    service = service_factory(model=model, transport=mcp, limits=AgentLimits(max_parallel_tools=2))
    handle = await service.open(identity=identity, message="Balance")
    await handle.task
    assert mcp.maximum == expected


async def test_price_guard_stops_before_model_call(service_factory, identity):
    service = service_factory(limits=AgentLimits(max_usd_per_turn=0.000001))
    service.config["azure_openai"] = {"input_usd_per_1m": 1, "output_usd_per_1m": 2}
    handle = await service.open(identity=identity, message="Hello")
    await handle.task
    assert handle.outcome.status == "limit_reached"
    assert not service.model.requests
    assert handle.outcome.persisted
