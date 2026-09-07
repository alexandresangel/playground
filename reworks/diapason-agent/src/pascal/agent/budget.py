"""Bound model context and tool payloads without persisting a second memory system."""

import json

import tiktoken


class BudgetExceeded(ValueError):
    pass


class ContextBudget:
    def __init__(self, max_context: int, max_output: int):
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.available = max_context - max_output - 256

    def count(self, value) -> int:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return len(self.encoding.encode(text, disallowed_special=()))

    def truncate(self, value, limit: int) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        tokens = self.encoding.encode(text, disallowed_special=())
        if len(tokens) <= limit:
            return text
        suffix = "\n[Tool result truncated; request a smaller result if needed.]"
        return self.encoding.decode(tokens[: max(0, limit - self.count(suffix))]) + suffix

    def fit(self, messages: list[dict], tools: list[dict]) -> list[dict]:
        result = list(messages)
        # Only drop complete previous user/assistant turns, never current tool exchanges.
        users = [index for index, msg in enumerate(result) if msg["role"] == "user"]
        current = users[-1] if users else 1
        while self.count({"messages": result, "tools": tools}) > self.available:
            next_user = next(
                (i for i in range(2, current + 1) if result[i]["role"] == "user"), None
            )
            if next_user is None:
                raise BudgetExceeded("context_limit")
            result = [result[0], *result[next_user:]]
            current -= next_user - 1
        return result


def cost_usd(usage: dict, rates: dict) -> float | None:
    if not usage:
        return None
    if not rates.get("input_usd_per_1m") or not rates.get("output_usd_per_1m"):
        return None
    cached = min(usage.get("cached_input", 0), usage.get("input", 0))
    return (
        (usage.get("input", 0) - cached) * float(rates["input_usd_per_1m"])
        + cached * float(rates.get("cached_input_usd_per_1m", rates["input_usd_per_1m"]))
        + usage.get("output", 0) * float(rates["output_usd_per_1m"])
    ) / 1_000_000
