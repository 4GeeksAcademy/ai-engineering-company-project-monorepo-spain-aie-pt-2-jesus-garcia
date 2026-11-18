"""Canal WebSocket del First-line CX agent (chat en tiempo real)."""

from __future__ import annotations

from .config import AGENT_ID
from .schemas import ChatMessageView, ChatSessionView, SessionSnapshotView
from .service import ChatService, get_chat_service, reset_chat_service, set_chat_service

__all__ = [
    "AGENT_ID",
    "ChatMessageView",
    "ChatService",
    "ChatSessionView",
    "SessionSnapshotView",
    "get_chat_service",
    "reset_chat_service",
    "set_chat_service",
]
