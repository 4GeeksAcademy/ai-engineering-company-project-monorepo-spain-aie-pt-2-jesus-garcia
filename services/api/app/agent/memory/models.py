"""Tablas SQLModel de la memoria del agente.

La memoria es un store aparte del RAG. No hay ninguna referencia a Qdrant ni a
la colección ``trackflow_knowledge``. El DDL canónico de PostgreSQL vive en
``services/api/migrations/0004_agent_memory.sql``; estos modelos lo replican
para SQLite (tests y ejecución local).
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .config import utcnow


def _uuid() -> str:
    return str(uuid4())


def _json_column() -> Column:
    return Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        server_default=text("'{}'"),
    )


_MEMORY_TYPE_CHECK = (
    "memory_type in ('carrier_rule', 'operational_context', 'client_preference')"
)
_SCOPE_CHECK = "scope_type in ('carrier', 'ops', 'client')"
_ENTRY_STATUS_CHECK = (
    "status in ('active', 'superseded', 'expired', 'stale', 'retired', 'blocked')"
)
_PROPOSAL_STATUS_CHECK = (
    "status in ('pending', 'approved', 'rejected', 'edited', 'blocked', 'expired')"
)


class AgentMemoryEntry(SQLModel, table=True):
    """Hecho aprobado que el agente puede recordar entre conversaciones."""

    __tablename__ = "agent_memory_entries"
    __table_args__ = (
        CheckConstraint(_MEMORY_TYPE_CHECK, name="ck_agent_memory_entry_type"),
        CheckConstraint(_SCOPE_CHECK, name="ck_agent_memory_entry_scope"),
        CheckConstraint(_ENTRY_STATUS_CHECK, name="ck_agent_memory_entry_status"),
        Index("ix_agent_memory_entries_scope_status", "scope_key", "status"),
        Index("ix_agent_memory_entries_type_status", "memory_type", "status"),
        Index("ix_agent_memory_entries_review", "status", "review_at"),
        # Una sola regla activa por alcance. Al corregir, la anterior pasa a
        # ``superseded`` y se conserva el histórico versionado.
        Index(
            "ux_agent_memory_active_scope",
            "scope_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    memory_type: str = Field(sa_column=Column(String, nullable=False))
    scope_type: str = Field(sa_column=Column(String, nullable=False))
    scope_key: str = Field(sa_column=Column(String, nullable=False))
    scope_label: str = Field(default="", sa_column=Column(String, nullable=False))
    scope_json: dict = Field(default_factory=dict, sa_column=_json_column())
    fact: str = Field(sa_column=Column(Text, nullable=False))
    reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(
        default="active",
        sa_column=Column(String, nullable=False, server_default="active"),
    )
    version: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1"),
    )
    supersedes_id: str | None = Field(default=None, sa_column=Column(String))
    source_proposal_id: str | None = Field(default=None, sa_column=Column(String))
    created_by: str = Field(sa_column=Column(String, nullable=False))
    approved_by: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    review_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class AgentMemoryProposal(SQLModel, table=True):
    """Propuesta pendiente o resuelta. Es también el registro de decisión."""

    __tablename__ = "agent_memory_proposals"
    __table_args__ = (
        CheckConstraint(_MEMORY_TYPE_CHECK, name="ck_agent_memory_proposal_type"),
        CheckConstraint(_SCOPE_CHECK, name="ck_agent_memory_proposal_scope"),
        CheckConstraint(
            _PROPOSAL_STATUS_CHECK, name="ck_agent_memory_proposal_status"
        ),
        Index(
            "ix_agent_memory_proposals_user_created", "user_id", "created_at"
        ),
        Index("ix_agent_memory_proposals_session", "session_id"),
        Index("ix_agent_memory_proposals_status", "status"),
        # Una sola propuesta pendiente por usuario. Se refuerza en base de
        # datos además de comprobarlo el store.
        Index(
            "ux_agent_memory_pending_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(sa_column=Column(String, nullable=False))
    user_id: str = Field(sa_column=Column(String, nullable=False))
    run_id: str | None = Field(default=None, sa_column=Column(String))
    memory_type: str = Field(sa_column=Column(String, nullable=False))
    scope_type: str = Field(sa_column=Column(String, nullable=False))
    scope_key: str = Field(sa_column=Column(String, nullable=False))
    scope_label: str = Field(default="", sa_column=Column(String, nullable=False))
    scope_json: dict = Field(default_factory=dict, sa_column=_json_column())
    fact: str = Field(sa_column=Column(Text, nullable=False))
    reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    source_quote: str = Field(default="", sa_column=Column(Text, nullable=False))
    status: str = Field(
        default="pending",
        sa_column=Column(String, nullable=False, server_default="pending"),
    )
    decision_label: str | None = Field(default=None, sa_column=Column(String))
    decision_confidence: float | None = Field(
        default=None, sa_column=Column(Float, nullable=True)
    )
    decision_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    decision_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    resulting_entry_id: str | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    validation_code: str | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    validation_detail: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    expires_at: datetime = Field(
        default_factory=lambda: utcnow(),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AgentMemoryAudit(SQLModel, table=True):
    """Log append-only de propuestas, decisiones, bloqueos y consolidación."""

    __tablename__ = "agent_memory_audit"
    __table_args__ = (
        Index("ix_agent_memory_audit_at", "at"),
        Index("ix_agent_memory_audit_action", "action"),
        Index("ix_agent_memory_audit_proposal", "proposal_id"),
        Index("ix_agent_memory_audit_entry", "entry_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    actor_user_id: str | None = Field(default=None, sa_column=Column(String))
    session_id: str | None = Field(default=None, sa_column=Column(String))
    action: str = Field(sa_column=Column(String, nullable=False))
    proposal_id: str | None = Field(default=None, sa_column=Column(String))
    entry_id: str | None = Field(default=None, sa_column=Column(String))
    origin_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    origin_message_hash: str | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    detail: dict = Field(default_factory=dict, sa_column=_json_column())


def create_agent_memory_tables(engine) -> None:
    """Crea las tablas si no existen (SQLite local y tests)."""

    for model in (AgentMemoryEntry, AgentMemoryProposal, AgentMemoryAudit):
        model.__table__.create(engine, checkfirst=True)


__all__ = [
    "AgentMemoryAudit",
    "AgentMemoryEntry",
    "AgentMemoryProposal",
    "create_agent_memory_tables",
]
