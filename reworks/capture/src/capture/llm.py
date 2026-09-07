"""Azure OpenAI adapter for the unchanged capture prompt interaction."""

from __future__ import annotations

from typing import Any

from openai import AsyncAzureOpenAI

from capture.config import azure_openai_config


class AzureCaptureLlm:
    def __init__(self, config: dict[str, Any]) -> None:
        block = azure_openai_config(config)
        endpoint = str(block.get("endpoint") or "").strip()
        api_key = str(block.get("api_key") or "").strip()
        self.deployment = str(block.get("deployment") or "").strip()
        api_version = str(block.get("api_version") or "2024-10-21").strip()
        if not endpoint or not api_key or not self.deployment:
            raise RuntimeError("Azure OpenAI endpoint, api_key, and deployment are required")
        self._client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

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
