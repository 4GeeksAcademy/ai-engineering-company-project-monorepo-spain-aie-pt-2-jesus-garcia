"""Contratos públicos del chat (REST y snapshot WebSocket)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .config import AGENT_ID


class ChatSessionCreate(BaseModel):
    client_id: str | None = Field(default=None, max_length=100)


class ChatSessionView(BaseModel):
    session_id: str
    thread_id: str
    agent_id: str = AGENT_ID
    user_id: str
    client_id: str | None = None
    status: str
    created_at: str


class ChatMessageView(BaseModel):
    message_id: str
    session_id: str
    role: str
    text: str
    status: str
    sequence: int = 0
    run_id: str | None = None
    created_at: str


class ActiveGenerationView(BaseModel):
    message_id: str
    run_id: str
    sequence: int = 0
    text: str = ""


class SessionSnapshotView(BaseModel):
    event: str = "session_snapshot"
    session_id: str
    thread_id: str
    agent_id: str = AGENT_ID
    status: str
    messages: list[ChatMessageView] = Field(default_factory=list)
    active_generation: ActiveGenerationView | None = None


__all__ = [
    "ActiveGenerationView",
    "ChatMessageView",
    "ChatSessionCreate",
    "ChatSessionView",
    "SessionSnapshotView",
]
