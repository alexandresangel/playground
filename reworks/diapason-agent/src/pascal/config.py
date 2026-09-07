"""Legacy JSON shape plus validated agent limits; no import-time configuration."""

import json
import math
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgentLimits(BaseModel):
    max_tool_rounds: int = Field(default=4, ge=0, le=20)
    max_tool_calls: int = Field(default=16, ge=1, le=128)
    max_parallel_tools: int = Field(default=4, ge=1, le=16)
    max_context_tokens: int = Field(default=24000, ge=1024)
    max_output_tokens: int = Field(default=2048, ge=64)
    max_tool_result_tokens: int = Field(default=4000, ge=128)
    max_message_chars: int = Field(default=32000, ge=1)
    max_tool_argument_chars: int = Field(default=64000, ge=1024)
    max_mcp_response_bytes: int = Field(default=2097152, ge=1024)
    catalogue_ttl_seconds: int = Field(default=300, ge=1)
    catalogue_max_entries: int = Field(default=128, ge=1)
    turn_timeout_seconds: float = Field(default=210, gt=0)
    model_timeout_seconds: float = Field(default=60, gt=0)
    model_retries: int = Field(default=2, ge=0, le=3)
    max_active_turns: int = Field(default=20, ge=1)
    stream_buffer_events: int = Field(default=128, ge=4)
    shutdown_grace_seconds: float = Field(default=20, gt=0)
    max_usd_per_turn: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def output_fits(self):
        if self.max_output_tokens + 256 >= self.max_context_tokens:
            raise ValueError("max_context_tokens must leave room for input and output")
        return self


def load_config(base_dir: Path | None = None) -> dict[str, Any]:
    root = base_dir or Path(os.getenv("PASCAL_ROOT") or Path.cwd())
    raw = (os.getenv("CHAT_CONFIG") or "").strip()
    if not raw:
        path = root / "config.json"
        if not path.is_file():
            raise RuntimeError("Set CHAT_CONFIG or create config.json in PASCAL_ROOT")
        raw = path.read_text(encoding="utf-8")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("CHAT_CONFIG must be a JSON object")
    return result


def limits_from_config(config: dict) -> AgentLimits:
    ao = config.get("azure_openai") or {}
    for key in ("input_usd_per_1m", "output_usd_per_1m", "cached_input_usd_per_1m"):
        if key in ao and (not math.isfinite(float(ao[key])) or float(ao[key]) < 0):
            raise ValueError(f"azure_openai.{key} must be finite and nonnegative")
    values = {"max_tool_rounds": ao.get("max_tool_rounds", 4), **(config.get("agent") or {})}
    limits = AgentLimits.model_validate(values)
    if limits.max_usd_per_turn is not None:
        for key in ("input_usd_per_1m", "output_usd_per_1m"):
            if float(ao.get(key, 0)) <= 0:
                raise ValueError(f"azure_openai.{key} must be positive when enforcing cost limits")
    return limits
