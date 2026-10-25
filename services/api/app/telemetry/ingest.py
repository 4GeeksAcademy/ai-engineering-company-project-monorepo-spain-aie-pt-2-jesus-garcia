"""Ingesta real de telemetría: validación por ítem + persistencia en bulk.

El envelope Pydantic (`TelemetryEvent`) se usa como validador de cada evento,
no como tipo del body completo. Así un evento inválido se rechaza de forma
individual y el resto del lote se persiste igual.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from app.telemetry.barriers import apply_barriers
from models import TelemetryEvent, TelemetryEventRecord

logger = logging.getLogger("api.telemetry")


@dataclass(frozen=True)
class IngestResult:
    received: int
    stored: int
    rejected: int


def parse_events(raw_events: list[Any]) -> tuple[list[TelemetryEvent], Counter]:
    """Valida cada elemento del lote; los inválidos no interrumpen el resto."""

    valid: list[TelemetryEvent] = []
    invalid_reasons: Counter = Counter()

    for raw in raw_events:
        if not isinstance(raw, dict):
            invalid_reasons["not_an_object"] += 1
            continue
        try:
            valid.append(TelemetryEvent.model_validate(raw))
        except ValidationError as exc:
            errors = exc.errors()
            if errors:
                location = errors[0].get("loc") or ()
                reason = ".".join(str(part) for part in location) or errors[0].get(
                    "type", "validation_error"
                )
            else:
                reason = "validation_error"
            invalid_reasons[reason] += 1

    return valid, invalid_reasons


def deduplicate(events: list[TelemetryEvent]) -> tuple[list[TelemetryEvent], int]:
    """Elimina `event_id` repetidos dentro del mismo lote (primero gana)."""

    unique: dict[str, TelemetryEvent] = {}
    duplicates = 0
    for event in events:
        if event.event_id in unique:
            duplicates += 1
            continue
        unique[event.event_id] = event
    return list(unique.values()), duplicates


def to_row(event: TelemetryEvent) -> dict:
    """Mapea el envelope validado a las columnas fijas + `tags` JSONB."""

    timestamp = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)

    return {
        "event_id": event.event_id,
        "timestamp": timestamp,
        "event_type": event.event_type.value,
        "service": event.app.value,
        "session_id": event.session_id,
        "user_id": (event.user_id or "").strip() or None,
        "schema_version": event.schema_version,
        "request_id": (event.request_id or "").strip() or None,
        "source": event.source.value,
        "tags": event.properties or {},
    }


def _build_insert_statement(session: Session):
    table = TelemetryEventRecord.__table__
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert(table).on_conflict_do_nothing(
            index_elements=["event_id"]
        )
    if dialect == "sqlite":
        return sqlite_insert(table).on_conflict_do_nothing(
            index_elements=["event_id"]
        )
    return insert(table)


def store_rows(session: Session, rows: list[dict]) -> int:
    """Un único INSERT (executemany) en una sola transacción.

    `ON CONFLICT (event_id) DO NOTHING` hace idempotentes los reintentos del
    frontend: el mismo evento no se duplica y no se cuenta como guardado.
    """

    if not rows:
        return 0

    result = session.execute(_build_insert_statement(session), rows)
    session.commit()

    stored = result.rowcount
    if stored is None or stored < 0:
        stored = len(rows)
    return stored


def ingest_batch(
    raw_events: list[Any],
    *,
    environment: str,
    consent: str,
    allow_non_production: bool,
    session: Session,
) -> IngestResult:
    received = len(raw_events)

    valid_events, invalid_reasons = parse_events(raw_events)
    accepted_events, accepted_counts, dropped_counts, drop_reasons = apply_barriers(
        valid_events,
        environment=environment,
        consent=consent,
        allow_non_production=allow_non_production,
    )
    unique_events, duplicates = deduplicate(accepted_events)
    rows = [to_row(event) for event in unique_events]

    stored = store_rows(session, rows)
    rejected = received - stored

    logger.info(
        "Telemetry events accepted: %d | dropped: %d | accepted_by_type: %s | dropped_by_type: %s",
        len(accepted_events),
        sum(dropped_counts.values()),
        dict(accepted_counts),
        dict(dropped_counts),
    )
    logger.info(
        "Telemetry events stored: %d | rejected: %d | invalid=%s | dropped=%s | duplicates=%d",
        stored,
        rejected,
        dict(invalid_reasons),
        dict(drop_reasons),
        duplicates,
    )

    return IngestResult(received=received, stored=stored, rejected=rejected)
