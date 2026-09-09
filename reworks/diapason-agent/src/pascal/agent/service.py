"""Own one turn from admission through graph execution and transcript persistence."""

import asyncio
import time
from dataclasses import dataclass, field

from langsmith import tracing_context
from opentelemetry.trace import Status, StatusCode

from pascal.agent.budget import BudgetExceeded, ContextBudget, cost_usd
from pascal.agent.graph import GraphContext, build_graph
from pascal.agent.state import ExternalFailure, TurnOutcome
from pascal.config import AgentLimits
from pascal.observability.events import completion, log
from pascal.observability.telemetry import operation
from pascal.tools.routing import route

MODE = "mcp-http+azure-tool-calling"


class BusyError(RuntimeError):
    pass


@dataclass
class TurnHandle:
    session_id: str
    outcome: TurnOutcome = field(default_factory=TurnOutcome)
    queue: asyncio.Queue | None = None
    task: asyncio.Task | None = None
    disconnected: bool = False
    entered: bool = False

    async def emit(self, event: dict):
        if self.queue is not None and not self.disconnected:
            await self.queue.put(event)

    async def disconnect(self):
        self.disconnected = True
        if self.task and not self.task.done():
            # If cancelled before its first instruction, a coroutine never reaches
            # finally. Let the owned producer enter and observe disconnected instead.
            if self.entered:
                self.task.cancel()
            try:
                await asyncio.shield(self.task)
            except asyncio.CancelledError:
                pass

    def payload(self, rates: dict) -> dict:
        outcome = self.outcome
        usage = {**outcome.usage, "cost_usd": cost_usd(outcome.usage, rates)}
        return dict(
            answer_markdown=outcome.answer,
            session_id=self.session_id,
            mode=MODE,
            tool_trace=outcome.traces,
            sources=outcome.sources,
            usage=usage,
            chart_spec=None,
            chart_reason=None,
            status=outcome.status,
            persisted=outcome.persisted,
        )


class ChatService:
    def __init__(self, *, model, transport, registry, store, prompts, config, limits: AgentLimits):
        self.model, self.transport, self.registry, self.store = model, transport, registry, store
        self.prompts, self.config, self.limits = prompts, config, limits
        self.graph = build_graph()
        self.active: dict[tuple[str, str], TurnHandle] = {}
        self.tasks: set[asyncio.Task] = set()
        self.closing = False
        self.preparing = 0

    async def open(
        self,
        *,
        identity,
        message,
        session_id=None,
        locale="en_us",
        timezone=None,
        streaming=False,
        external=None,
    ) -> TurnHandle:
        started = time.monotonic()
        deadline = asyncio.get_running_loop().time() + self.limits.turn_timeout_seconds
        if self.closing or len(self.tasks) + self.preparing >= self.limits.max_active_turns:
            raise BusyError("Agent is busy; retry shortly")
        if not message.strip() or len(message) > self.limits.max_message_chars:
            raise ValueError("Message is empty or too long")
        self.preparing += 1
        key = None
        reserved = False
        try:
            async with asyncio.timeout_at(deadline):
                if external is None:
                    catalogue = await self.registry.discover(identity.mcp, identity.scope_path)
                    text, tools, direct = route(message, catalogue)
                else:
                    text, tools, direct = message, [], None
                sid = await asyncio.to_thread(
                    self.store.resolve_session_id, identity.scope_path, session_id
                )
                key = (identity.scope_path, sid)
                if key in self.active:
                    raise BusyError("This session already has an active turn")
                handle = TurnHandle(
                    sid,
                    queue=asyncio.Queue(self.limits.stream_buffer_events) if streaming else None,
                )
                self.active[key] = handle
                reserved = True
                history = (
                    await asyncio.to_thread(self.store.get_turns, sid, identity.scope_path)
                    if external is None
                    else []
                )
                messages, version = self.prompts.compose(history, text, locale, timezone)
                budget = ContextBudget(
                    self.limits.max_context_tokens, self.limits.max_output_tokens
                )
                # Reject oversized input before a streaming response starts.
                budget.fit(messages, [tool.definition for tool in tools])
            handle.task = asyncio.create_task(
                self._run(
                    handle,
                    identity,
                    message,
                    messages,
                    tools,
                    direct,
                    locale,
                    budget,
                    version,
                    external,
                    started,
                    deadline,
                ),
                name="pascal-turn",
            )
            self.tasks.add(handle.task)
            handle.task.add_done_callback(self.tasks.discard)
            return handle
        except BaseException:
            if reserved and key in self.active and self.active[key].task is None:
                self.active.pop(key, None)
            raise
        finally:
            self.preparing -= 1

    async def _run(
        self,
        handle,
        identity,
        original,
        messages,
        tools,
        direct,
        locale,
        budget,
        version,
        external,
        started,
        deadline,
    ):
        handle.entered = True
        outcome = handle.outcome
        with operation("chat.completion") as span:
            span.set_attribute("chat.session_id", handle.session_id)
            span.set_attribute("chat.prompt_version", version)
            try:
                if handle.disconnected:
                    raise asyncio.CancelledError
                async with asyncio.timeout_at(deadline):
                    if external is not None:
                        result = await external(handle.session_id)
                        outcome.public_result = result.result
                        outcome.answer = result.answer
                        outcome.receipt = result.receipt
                    elif direct is not None:
                        outcome.answer = direct
                        await handle.emit({"type": "delta", "content": direct})
                    else:
                        context = GraphContext(
                            self.model,
                            self.transport,
                            tools,
                            self.limits,
                            budget,
                            self.config.get("azure_openai", {}),
                            outcome,
                            locale,
                            started,
                        )
                        # Do not allow ambient LANGSMITH_* settings to export conversation data.
                        with tracing_context(enabled=False):
                            async for event in self.graph.astream(
                                {
                                    "messages": messages,
                                    "pending": [],
                                    "rounds": 0,
                                    "tool_count": 0,
                                    "stop": False,
                                },
                                context=context,
                                config={"recursion_limit": self.limits.max_tool_rounds * 2 + 5},
                                stream_mode="custom",
                            ):
                                await handle.emit(event)
                    outcome.status = "completed"
            except asyncio.CancelledError:
                outcome.status = "cancelled"
            except TimeoutError:
                outcome.status = "timeout"
            except BudgetExceeded:
                outcome.status = "limit_reached"
            except ExternalFailure as exc:
                outcome.status = "failed"
                outcome.error_status = exc.status_code
            except Exception as exc:
                outcome.status = "failed"
                log.warning("chat execution failed error_type=%s", type(exc).__name__)
            finally:
                if outcome.status != "completed":
                    notice = (
                        "\n\nThe response was interrupted or could not be completed. "
                        "Any displayed results may be partial."
                    )
                    outcome.answer += notice
                if not outcome.answer.strip():
                    outcome.answer = "No answer was returned. Please try again."
                # Shield the write from a disconnected response task. It remains owned and awaited.
                persist = asyncio.create_task(
                    asyncio.to_thread(
                        self.store.append_turn,
                        handle.session_id,
                        identity.scope_path,
                        original,
                        outcome.answer,
                        tool_trace=outcome.traces,
                        sources=outcome.sources,
                        usage={
                            **outcome.usage,
                            "cost_usd": cost_usd(
                                outcome.usage, self.config.get("azure_openai", {})
                            ),
                        },
                        capture_receipt=outcome.receipt,
                    ),
                    name="pascal-persist",
                )
                try:
                    try:
                        await asyncio.shield(persist)
                    except asyncio.CancelledError:
                        await persist
                    outcome.persisted = True
                except Exception as exc:
                    outcome.status = "persistence_failed"
                    log.error("chat persistence failed error_type=%s", type(exc).__name__)
                finally:
                    self.active.pop((identity.scope_path, handle.session_id), None)
                span.set_attribute("chat.status", outcome.status)
                span.set_attribute("chat.persisted", outcome.persisted)
                if outcome.status != "completed":
                    span.set_status(Status(StatusCode.ERROR))
                    span.set_attribute("error.type", outcome.status)
                completion(
                    identity,
                    handle.session_id,
                    outcome,
                    self.config,
                    int((time.monotonic() - started) * 1000),
                    version,
                )
            if outcome.status != "completed":
                await handle.emit(
                    {"type": "error", "content": "Response incomplete", "status": outcome.status}
                )
            await handle.emit(
                {"type": "done", **handle.payload(self.config.get("azure_openai", {}))}
            )

    async def close(self):
        self.closing = True
        handles = list(self.active.values())
        tasks = list(self.tasks)
        if not tasks:
            return
        _, pending = await asyncio.wait(tasks, timeout=self.limits.shutdown_grace_seconds)
        by_task = {handle.task: handle for handle in handles}
        for task in pending:
            handle = by_task.get(task)
            if handle:
                handle.disconnected = True
            if handle is None or handle.entered:
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
