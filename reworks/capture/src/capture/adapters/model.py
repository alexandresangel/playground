"""Azure OpenAI adapter for the unchanged capture prompt interaction."""

from __future__ import annotations

from typing import Any

import httpx

from capture.adapters.azure_openai import AzureOpenAISettings, create_async_client
from capture.config import azure_openai_config


class CaptureModel:
    def __init__(
        self, config: dict[str, Any], *, http_client: httpx.AsyncClient | None = None
    ) -> None:
        block = azure_openai_config(config)
        settings = AzureOpenAISettings.from_mapping(block)
        self.deployment = settings.deployment
        self._client = create_async_client(
            settings,
            timeout_seconds=float(block.get("timeout_seconds", 120)),
            max_retries=int(block.get("max_retries", 2)),
            http_client=http_client,
        )

    async def close(self) -> None:
        await self._client.close()

    async def extract(
        self, *, prompt: str, document_text: str, temperature: float
    ) -> dict[str, Any]:
        response = await self._client.chat.completions.create(
            model=self.deployment,
            temperature=temperature,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Extract the trade as Diapason import XML from this document text. "
                        "Return XML only.\n\n"
                        f"{document_text}"
                    ),
                },
            ],
        )
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message else ""
        if not content:
            raise RuntimeError("Empty LLM response for trade XML extraction")
        usage = response.usage
        usage_data: dict[str, int] = {}
        if usage is not None:
            usage_data = {
                "input": int(getattr(usage, "prompt_tokens", 0) or 0),
                "output": int(getattr(usage, "completion_tokens", 0) or 0),
                "total": int(getattr(usage, "total_tokens", 0) or 0),
            }
        return {"content": content, "deployment": self.deployment, "usage": usage_data}
