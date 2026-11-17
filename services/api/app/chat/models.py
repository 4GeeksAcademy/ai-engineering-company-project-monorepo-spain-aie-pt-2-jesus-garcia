"""Tablas SQLModel del chat: sesión y mensajes.

El DDL canónico de PostgreSQL se crea con ``create_all`` en el lifespan de la
API (mismo patrón que ``agent_memory_*``), así que sirve tanto para SQLite
local/tests como para Supabase.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, Text, func
from sqlmodel import Field, SQLModel

from .config import AGENT_ID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _status_check(values: tuple[str, ...], name: str) -> CheckConstraint:
    quoted = ", ".join(f"'{value}'" for value in values)
    column = "status"
    return CheckConstraint(f"{column} in ({quoted})", name=name)


class ChatSessionRecord(SQLModel, table=True):
    """Conversación de chat ligada a un hilo de LangGraph."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        _status_check(("active", "interrupted", "closed"), "ck_chat_session_status"),
        Index("ix_chat_sessions_user_created", "user_id", "created_at"),
    )

    session_id: str = Field(primary_key=True)
    agent_id: str = Field(
        default=AGENT_ID,
        sa_column=Column(String, nullable=False, server_default=AGENT_ID),
    )
    user_id: str = Field(sa_column=Column(String, nullable=False))
    client_id: str | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    status: str = Field(
        default="active",
        sa_column=Column(String, nullable=False, server_default="active"),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )


class ChatMessageRecord(SQLModel, table=True):
    """Mensaje de usuario o de asistente dentro de una sesión."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(
            "role in ('user', 'assistant')", name="ck_chat_message_role"
        ),
        _status_check(
            ("streaming", "completed", "interrupted", "failed"),
            "ck_chat_message_status",
        ),
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
        Index("ix_chat_messages_status", "status"),
    )

    message_id: str = Field(primary_key=True)
    session_id: str = Field(sa_column=Column(String, nullable=False))
    role: str = Field(sa_column=Column(String, nullable=False))
    text: str = Field(
        default="", sa_column=Column(Text, nullable=False, server_default="")
    )
    status: str = Field(
        default="streaming",
        sa_column=Column(String, nullable=False, server_default="streaming"),
    )
    sequence: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    run_id: str | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )


def create_chat_tables(engine) -> None:
    """Crea las tablas si no existen (idempotente)."""

    for model in (ChatSessionRecord, ChatMessageRecord):
        model.__table__.create(engine, checkfirst=True)


__all__ = [
    "ChatMessageRecord",
    "ChatSessionRecord",
    "create_chat_tables",
]
