"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, examples=["Show me noise-cancelling headphones under $300"])
    user_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-.@]+$", examples=["web-3f9a"])
    session_id: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9_\-]+$")
    customer_id: str = Field(default="CUST-001", pattern=r"^CUST-\d{3}$", description="Demo signed-in customer")


class ToolCall(BaseModel):
    agent: str | None
    name: str
    args: dict[str, Any] = {}


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    agents: list[str]
    tool_calls: list[ToolCall]
    latency_ms: float


class SessionCreate(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-.@]+$")
    customer_id: str = Field(default="CUST-001", pattern=r"^CUST-\d{3}$")
    agent: str = "coordinator"


class SessionSummary(BaseModel):
    session_id: str
    app_name: str
    user_id: str
    last_update_time: float
    title: str | None = None
    state: dict[str, Any] = {}


class Message(BaseModel):
    role: str  # user | assistant | tool
    author: str
    text: str
    timestamp: float


class SessionDetail(SessionSummary):
    messages: list[Message]


class AgentInfo(BaseModel):
    key: str
    name: str
    description: str
    sub_agents: list[str]
    tools: list[str]
