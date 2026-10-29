"""Outbox transaccional de telemetría.

La orden/discrepancia y su evento se escriben en la misma transacción. El relay
del pipeline (`pipelines.weekly_performance.outbox`) mueve los pendientes a
`telemetry_events` con `ON CONFLICT (event_id) DO NOTHING`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import JSON, Column, DateTime, Engine, Integer, MetaData, String, Table, insert, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Session

from app.telemetry.emitter import log_event
from models import TelemetryEvent


def _json_type():
    return JSON().with_variant(JSONB(), "postgresql")


@lru_cache(maxsize=2)
def _table(schema: str | None) -> Table:
    metadata = MetaData(schema=schema)
    return Table(
        "telemetry_outbox",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("event_id", String(36), nullable=False, unique=True),
        Column("payload", _json_type(), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("sent_at", DateTime(timezone=True)),
        Column("attempts", Integer, nullable=False, default=0),
        Column("last_error", String(2048)),
    )


def outbox_table(engine: Engine) -> Table:
    schema = "ops" if engine.dialect.name == "postgresql" else None
    return _table(schema)


def create_outbox_table(engine: Engine) -> None:
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS ops"))
    outbox_table(engine).metadata.create_all(engine)


def enqueue_event(session: Session, event: TelemetryEvent | None) -> bool:
    """Encola el evento en la transacción actual; no hace commit."""

    if event is None:
        return False

    table = outbox_table(session.get_bind())
    session.execute(
        insert(table).values(
            event_id=event.event_id,
            payload=event.model_dump(mode="json"),
            created_at=datetime.now(timezone.utc),
            attempts=0,
        )
    )
    log_event(event)
    return True


def count_pending(session: Session) -> int:
    table = outbox_table(session.get_bind())
    from sqlalchemy import func, select

    return int(
        session.execute(
            select(func.count()).select_from(table).where(table.c.sent_at.is_(None))
        ).scalar()
        or 0
    )
