"""Relay idempotente del outbox transaccional.

La API escribe la orden/discrepancia y su evento en ``ops.telemetry_outbox``
dentro de la misma transacción. Este relay mueve los pendientes a
``telemetry_events`` con ``ON CONFLICT (event_id) DO NOTHING``: reintentar no
duplica y un fallo deja el evento pendiente para la siguiente pasada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy import Engine, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .schema import outbox_table, telemetry_table
from .sql import ops_schema_for

logger = logging.getLogger("pipeline.outbox")


@dataclass(frozen=True)
class RelayResult:
    relayed: int
    duplicates: int


def relay_outbox(engine: Engine, batch_size: int = 100) -> RelayResult:
    """Mueve hasta ``batch_size`` eventos pendientes del outbox a telemetría."""

    outbox = outbox_table(ops_schema_for(engine))
    telemetry = telemetry_table()
    now = datetime.now(timezone.utc)

    with engine.begin() as conn:
        stmt = (
            select(outbox.c.id, outbox.c.event_id, outbox.c.payload)
            .where(outbox.c.sent_at.is_(None))
            .order_by(outbox.c.id)
            .limit(batch_size)
        )
        if engine.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        pending = conn.execute(stmt).mappings().all()
        if not pending:
            return RelayResult(relayed=0, duplicates=0)

        events = [_to_event(row) for row in pending]
        dialect = engine.dialect.name
        if dialect == "postgresql":
            insert_stmt = postgresql_insert(telemetry).on_conflict_do_nothing(
                index_elements=["event_id"]
            )
        elif dialect == "sqlite":
            insert_stmt = sqlite_insert(telemetry).on_conflict_do_nothing(
                index_elements=["event_id"]
            )
        else:  # pragma: no cover - no hay otros dialectos soportados
            insert_stmt = telemetry.insert()

        event_ids = [event["event_id"] for event in events]
        existing = {
            str(value)
            for value in conn.execute(
                select(telemetry.c.event_id).where(
                    telemetry.c.event_id.in_(event_ids)
                )
            ).scalars().all()
        }
        new_events = [
            event for event in events if event["event_id"] not in existing
        ]
        duplicates = len(events) - len(new_events)
        relayed = len(new_events)
        if new_events:
            conn.execute(insert_stmt, new_events)

        conn.execute(
            update(outbox)
            .where(outbox.c.id.in_([row["id"] for row in pending]))
            .values(sent_at=now, attempts=outbox.c.attempts + 1)
        )

    logger.info("Outbox relay: %s enviados, %s duplicados", relayed, duplicates)
    return RelayResult(relayed=relayed, duplicates=duplicates)


def _to_event(row: Any) -> dict:
    payload = row["payload"] or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Payload de outbox inválido en id={row['id']}")

    timestamp = payload.get("timestamp")
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if not isinstance(timestamp, datetime):
        timestamp = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return {
        "event_id": str(payload.get("event_id") or row["event_id"]),
        "timestamp": timestamp,
        "event_type": payload.get("event_type") or "unknown",
        "session_id": payload.get("session_id") or "outbox",
        "user_id": payload.get("user_id"),
        "schema_version": payload.get("schema_version") or "2.0.0",
        "request_id": payload.get("request_id"),
        "source": payload.get("source") or "backend",
        "service": payload.get("service") or payload.get("app") or "backoffice",
        "tags": payload.get("properties") or payload.get("tags") or {},
        "received_at": datetime.now(timezone.utc),
    }
