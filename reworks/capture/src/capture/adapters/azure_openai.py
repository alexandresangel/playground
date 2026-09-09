"""One Azure OpenAI client factory for async Python applications.

v1 uses the standard OpenAI SDK client. Dated Azure endpoints are an explicit
migration adapter, not a second model implementation. Never infer credentials
from an unrelated OpenAI account's ambient environment.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from openai import AsyncAzureOpenAI, AsyncOpenAI


@dataclass(frozen=True)
class AzureOpenAISettings:
    endpoint: str
    deployment: str
    api_key: str = field(repr=False)
    api_mode: Literal["v1", "azure_dated"] = "v1"
    api_version: str | None = None

    @classmethod
    def from_mapping(cls, block: Mapping[str, Any]) -> "AzureOpenAISettings":
        endpoint = str(block.get("base_url") or block.get("endpoint") or "").strip().rstrip("/")
        deployment = str(block.get("deployment") or "").strip()
        api_key = str(block.get("api_key") or "").strip()
        mode = str(block.get("api_mode") or "v1").strip()
        version = str(block.get("api_version") or "").strip() or None
        parsed = urlsplit(endpoint)
        if not endpoint or not deployment or not api_key:
            raise ValueError("Azure endpoint, deployment and api_key are required")
        if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
            raise ValueError(
                "Azure endpoint must be an absolute HTTPS URL without query or fragment"
            )
        if parsed.username or parsed.password:
            raise ValueError("Azure endpoint must not contain credentials")
        if mode not in {"v1", "azure_dated"}:
            raise ValueError("azure_openai.api_mode must be v1 or azure_dated")
        if mode == "azure_dated" and not version:
            raise ValueError("azure_dated mode requires an explicit api_version")
        if mode == "azure_dated" and parsed.path.rstrip("/").endswith("/openai/v1"):
            raise ValueError("A v1 endpoint cannot be used with azure_dated mode")
        # A dated api_version left in an old config cannot silently keep the app
        # on the old transport. It is unused in v1; migration docs call this out.
        return cls(endpoint, deployment, api_key, mode, version)

    @property
    def v1_base_url(self) -> str:
        suffix = "" if self.endpoint.endswith("/openai/v1") else "/openai/v1"
        return self.endpoint + suffix + "/"


def create_async_client(
    settings: AzureOpenAISettings,
    *,
    timeout_seconds: float = 60,
    max_retries: int = 2,
    http_client: httpx.AsyncClient | None = None,
) -> AsyncOpenAI:
    """The caller owns and closes the returned SDK client at application shutdown."""
    options: dict[str, Any] = {
        "api_key": settings.api_key,
        "timeout": timeout_seconds,
        "max_retries": max_retries,
    }
    if http_client is not None:
        options["http_client"] = http_client
    if settings.api_mode == "azure_dated":
        return AsyncAzureOpenAI(
            azure_endpoint=settings.endpoint,
            api_version=settings.api_version,
            **options,
        )
    return AsyncOpenAI(base_url=settings.v1_base_url, **options)
