"""Integración PostgreSQL (JSONB, UUID, advisory lock, upsert).

Se ejecuta solo si ``TEST_POSTGRES_URL`` apunta a una BD desechable:

    TEST_POSTGRES_URL=postgresql://postgres:test@localhost:55432/trackflow \\
      python -m pytest pipelines/weekly_performance/tests/test_postgres.py -q
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, select, text

from pipelines.weekly_performance.core import run_week
from pipelines.weekly_performance.locks import advisory_key
from pipelines.weekly_performance.outbox import relay_outbox
from pipelines.weekly_performance.schema import outbox_table, telemetry_table
from pipelines.weekly_performance.sql import (
    create_reporting_schema,
    create_telemetry_table,
    ops_schema_for,
    tables_for,
)
from pipelines.weekly_performance.tests.factories import WEEKS, seed_three_weeks

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL"),
    reason="TEST_POSTGRES_URL no configurada",
)


@pytest.fixture()
def pg_engine():
    engine = create_engine(
        os.environ["TEST_POSTGRES_URL"],
        connect_args={"options": "-c timezone=UTC"},
    )
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS reporting CASCADE"))
        conn.execute(text("DROP SCHEMA IF EXISTS ops CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS telemetry_events CASCADE"))
    create_reporting_schema(engine)
    create_telemetry_table(engine)
    seed_three_weeks(engine)
    yield engine
    engine.dispose()


def test_upsert_and_jsonb_on_postgres(pg_engine):
    result = run_week(pg_engine, WEEKS[0], triggered_by="pg-test")
    assert result.status == "success"
    assert result.rows_written == 2

    with pg_engine.connect() as conn:
        rows = conn.execute(select(tables_for(pg_engine).performance)).mappings().all()
        tags_type = conn.execute(
            text("select pg_typeof(tags) from telemetry_events limit 1")
        ).scalar()
    assert len(rows) == 2
    assert tags_type == "jsonb"


def test_advisory_lock_is_exclusive(pg_engine):
    key = advisory_key(WEEKS[0])
    first = pg_engine.connect()
    second = pg_engine.connect()
    try:
        assert (
            first.execute(text("select pg_try_advisory_lock(:key)"), {"key": key}).scalar()
            is True
        )
        assert (
            second.execute(
                text("select pg_try_advisory_lock(:key)"), {"key": key}
            ).scalar()
            is False
        )
        first.execute(text("select pg_advisory_unlock(:key)"), {"key": key})
        first.commit()
    finally:
        first.close()
        second.close()


def test_outbox_relay_is_idempotent_on_postgres(pg_engine):
    event_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "timestamp": "2026-07-06T10:00:00Z",
        "event_type": "inbound_order_created",
        "session_id": "pg",
        "schema_version": "2.0.0",
        "source": "backend",
        "app": "backoffice",
        "properties": {
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "quantity": 3,
        },
    }
    outbox = outbox_table(ops_schema_for(pg_engine))
    with pg_engine.begin() as conn:
        conn.execute(
            insert(outbox).values(
                event_id=event_id,
                payload=payload,
                created_at=datetime.now(timezone.utc),
                attempts=0,
            )
        )

    assert relay_outbox(pg_engine).relayed == 1
    assert relay_outbox(pg_engine).relayed == 0
    telemetry = telemetry_table()
    with pg_engine.connect() as conn:
        stored = conn.execute(
            select(telemetry.c.event_id).where(telemetry.c.event_id == event_id)
        ).first()
    assert stored is not None
