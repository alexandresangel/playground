"""Azure Chat Completions boundary; no synchronous SDK in the request loop."""

from collections.abc import Awaitable, Callable

from openai import AsyncAzureOpenAI

from pascal.agent.state import ModelReply, ToolCall
from pascal.config import AgentLimits


class AzureModel:
    def __init__(self, config: dict, limits: AgentLimits):
        self.config = config
        self.client = AsyncAzureOpenAI(
            azure_endpoint=config["endpoint"],
            api_key=config["api_key"],
            api_version=config.get("api_version", "2024-10-21"),
            timeout=limits.model_timeout_seconds,
            max_retries=limits.model_retries,
        )

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
        on_delta: Callable[[str], Awaitable[None]],
    ) -> ModelReply:
        kwargs = dict(
            model=self.config["deployment"],
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            temperature=self.config.get("temperature", 0.2),
        )
        # Older Azure deployments can explicitly opt out; never replay a partial stream.
        if self.config.get("stream_usage", True):
            kwargs["stream_options"] = {"include_usage": True}
        if tools:
            kwargs.update(tools=tools, tool_choice="auto")
        stream = await self.client.chat.completions.create(**kwargs)
        reply = ModelReply()
        calls: dict[int, dict] = {}
        async with stream:
            async for chunk in stream:
                if chunk.usage:
                    usage = chunk.usage
                    detail = usage.prompt_tokens_details
                    reply.usage = {
                        "input": usage.prompt_tokens,
                        "output": usage.completion_tokens,
                        "total": usage.total_tokens,
                        "cached_input": int(detail.cached_tokens or 0) if detail else 0,
                    }
                if not chunk.choices:
                    continue
                if chunk.choices[0].finish_reason:
                    reply.finish_reason = chunk.choices[0].finish_reason
                delta = chunk.choices[0].delta
                if delta.content:
                    reply.content += delta.content
                    await on_delta(delta.content)
                for fragment in delta.tool_calls or []:
                    item = calls.setdefault(fragment.index, {"id": "", "name": "", "arguments": ""})
                    if fragment.id:
                        item["id"] = fragment.id
                    if fragment.function:
                        item["name"] += fragment.function.name or ""
                        item["arguments"] += fragment.function.arguments or ""
        reply.tool_calls = [ToolCall(**calls[index]) for index in sorted(calls)]
        return reply

    async def close(self):
        await self.client.close()
