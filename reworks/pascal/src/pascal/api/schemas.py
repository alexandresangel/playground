"""Pascal request and response models."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    # IANA zone from the browser (e.g. Europe/Paris). Overrides context.timezone for this request.
    client_timezone: Optional[str] = None


class ChatResponse(BaseModel):
    answer_markdown: str
    session_id: str
    chart_spec: Optional[Dict[str, Any]] = None
    chart_reason: Optional[str] = None
    mode: str
    tool_trace: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, str]] = Field(default_factory=list)


class SessionCreateResponse(BaseModel):
    session_id: str
    created_at: str


class SessionDetailResponse(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    turns: List[Dict[str, Any]] = Field(default_factory=list)


class SessionSummary(BaseModel):
    session_id: str
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    has_response: bool = False


class SessionListResponse(BaseModel):
    sessions: List[SessionSummary] = Field(default_factory=list)


class McpToolInfo(BaseModel):
    name: str
    native_name: str
    mcp_server: str
    mcp_label: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    audience: str = "user"
    mentionable: bool = True
    # Friendly token for @ completion (no server__ prefix); routing accepts this too.
    mention_token: str = ""


class McpServerTools(BaseModel):
    server_id: str
    label: str
    mention_prefix: str = ""
    server_url: str
    ok: bool
    error: Optional[str] = None
    tools: List[McpToolInfo] = Field(default_factory=list)


class McpToolsListResponse(BaseModel):
    servers: List[McpServerTools] = Field(default_factory=list)
    tools: List[McpToolInfo] = Field(default_factory=list)


class MintTokenBody(BaseModel):
    sub: str
    roles: List[str] = Field(..., min_length=1)
    customer_id: Optional[int] = None
    ttl_days: Optional[int] = None
    ttl_seconds: Optional[int] = None


class RevokeTokenBody(BaseModel):
    jti: Optional[str] = None
    sub: Optional[str] = None
    reason: str = ""