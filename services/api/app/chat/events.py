"""Nombres canónicos del contrato WebSocket del chat.

No se reutilizan los eventos SSE de la Parte 1 (``rfp_ticket_created``,
``sla_threshold_alert``): este canal tiene su propio contrato y sus propias
entidades.
"""

from __future__ import annotations

SESSION_SNAPSHOT = "session_snapshot"
USER_MESSAGE = "user_message"
GENERATION_STARTED = "generation_started"
TOKEN_CHUNK = "token_chunk"
INTERRUPT_REQUESTED = "interrupt_requested"
GENERATION_INTERRUPTED = "generation_interrupted"
GENERATION_COMPLETED = "generation_completed"
ERROR = "error"
PING = "ping"
PONG = "pong"
AUTH = "auth"

EVENT_NAMES = (
    SESSION_SNAPSHOT,
    USER_MESSAGE,
    GENERATION_STARTED,
    TOKEN_CHUNK,
    INTERRUPT_REQUESTED,
    GENERATION_INTERRUPTED,
    GENERATION_COMPLETED,
    ERROR,
)

__all__ = [
    "AUTH",
    "ERROR",
    "EVENT_NAMES",
    "GENERATION_COMPLETED",
    "GENERATION_INTERRUPTED",
    "GENERATION_STARTED",
    "INTERRUPT_REQUESTED",
    "PING",
    "PONG",
    "SESSION_SNAPSHOT",
    "TOKEN_CHUNK",
    "USER_MESSAGE",
]
