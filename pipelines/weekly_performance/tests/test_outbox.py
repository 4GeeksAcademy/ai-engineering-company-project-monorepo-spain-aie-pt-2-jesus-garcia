from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import insert, select

from pipelines.weekly_performance.outbox import relay_outbox
from pipelines.weekly_performance.schema import outbox_table, telemetry_table
from pipelines.weekly_performance.sql import ops_schema_for

EVENT_1 = "00000000-0000-0000-0000-000000000001"
EVENT_2 = "00000000-0000-0000-0000-000000000002"


def _payload(event_id: str) -> dict:
    return {
        "event_id": event_id,
        "timestamp": "2026-07-06T10:00:00Z",
        "event_type": "inbound_order_created",
        "session_id": "outbox-test",
        "schema_version": "2.0.0",
        "source": "backend",
        "app": "backoffice",
        "properties": {
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "quantity": 10,
        },
    }


def _outbox(engine):
    return outbox_table(ops_schema_for(engine))


def _seed_outbox(engine, event_ids: list[str]):
    table = _outbox(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(table),
            [
                {
                    "event_id": event_id,
                    "payload": _payload(event_id),
                    "created_at": now,
                    "attempts": 0,
                }
                for event_id in event_ids
            ],
        )


def test_relay_moves_pending_events(engine):
    _seed_outbox(engine, [EVENT_1, EVENT_2])

    result = relay_outbox(engine)

    assert result.relayed == 2
    assert result.duplicates == 0
    with engine.connect() as conn:
        rows = conn.execute(select(telemetry_table().c.event_id)).scalars().all()
    assert len(rows) == 2


def test_relay_is_idempotent_for_duplicates(engine):
    telemetry = telemetry_table()
    with engine.begin() as conn:
        conn.execute(
            insert(telemetry).values(
                event_id=EVENT_1,
                timestamp=datetime(2026, 7, 6, 10, tzinfo=timezone.utc),
                event_type="inbound_order_created",
                session_id="existing",
                user_id=None,
                schema_version="2.0.0",
                request_id=None,
                source="backend",
                service="backoffice",
                tags={},
                received_at=datetime.now(timezone.utc),
            )
        )
    _seed_outbox(engine, [EVENT_1, EVENT_2])

    first = relay_outbox(engine)
    second = relay_outbox(engine)

    assert first.relayed == 1
    assert first.duplicates == 1
    assert second.relayed == 0
    with engine.connect() as conn:
        rows = conn.execute(select(telemetry.c.event_id)).scalars().all()
    assert sorted(str(value) for value in rows) == [EVENT_1, EVENT_2]
