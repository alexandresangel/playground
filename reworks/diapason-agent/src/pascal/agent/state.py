"""Only conversation state enters the graph; credentials live in runtime context."""

from dataclasses import dataclass, field
from typing import TypedDict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class ModelReply:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


class PascalState(TypedDict):
    messages: list[dict]
    pending: list[ToolCall]
    rounds: int
    tool_count: int
    stop: bool


@dataclass
class TurnOutcome:
    answer: str = ""
    traces: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    status: str = "running"
    rounds: int = 0
    first_token_ms: int | None = None
    persisted: bool = False
    public_result: dict | None = None
    receipt: dict | None = None
    error_status: int = 502


@dataclass
class ExternalResult:
    """An external workflow's public wire result plus its minimal chat receipt."""

    result: dict
    answer: str
    receipt: dict


class ExternalFailure(RuntimeError):
    def __init__(self, status_code: int):
        super().__init__("external_workflow_failed")
        self.status_code = status_code
