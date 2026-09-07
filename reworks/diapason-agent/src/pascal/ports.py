"""Small interfaces only where a production dependency is replaceable."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pascal.agent.state import ModelReply


class Model(Protocol):
    async def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
        on_delta: Callable[[str], Awaitable[None]],
    ) -> ModelReply: ...


class McpTransport(Protocol):
    async def request(self, server: Any, method: str, params: dict) -> dict: ...


class SessionStore(Protocol):
    backend: str

    def resolve_session_id(self, scope: str, session_id: str | None) -> str: ...
    def get_turns(self, session_id: str, scope: str) -> list[dict]: ...
    def append_turn(
        self, session_id: str, scope: str, user: str, assistant: str, **kwargs: Any
    ) -> None: ...
    def create_session(self, scope: str, title: str = "") -> dict: ...
    def get_session(self, session_id: str, scope: str | None = None) -> dict | None: ...
    def list_sessions(self, scope: str) -> list[dict]: ...
    def delete_session(self, session_id: str, scope: str) -> bool: ...
