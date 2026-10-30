"""Contexto común para los tests del job runner y del script nocturno."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import text
from sqlmodel import create_engine

# pytest inserta ``tests/jobs`` en ``sys.path``, no la raíz del monorepo.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# El script importa el pipeline solo como subproceso, pero se evita cualquier
# intento de Prefect de hablar con su API durante los tests.
os.environ.setdefault("PREFECT_LOGGING_TO_API_ENABLED", "false")
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")

from services.job_runner.models import create_job_runs_table  # noqa: E402

#: Reflejo mínimo de ``telemetry_events`` para probar el export sin Supabase.
TELEMETRY_DDL = """
create table if not exists telemetry_events (
    event_id       text primary key,
    timestamp      timestamp not null,
    received_at    timestamp,
    event_type     text,
    service        text,
    session_id     text,
    user_id        text,
    schema_version text,
    request_id     text,
    source         text,
    tags           json
)
"""


@pytest.fixture()
def engine(tmp_path):
    """SQLite aislado por test con ``job_runs`` y ``telemetry_events``."""

    eng = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    create_job_runs_table(eng)
    with eng.begin() as connection:
        connection.execute(text(TELEMETRY_DDL))
    return eng


def sqlite_timestamp(value) -> str:
    """Formato que usa el dialecto SQLite de SQLAlchemy para DATETIME."""

    return value.strftime("%Y-%m-%d %H:%M:%S.%f")


@pytest.fixture()
def insert_events(engine):
    """Inserta ``(event_id, timestamp, tags)`` en ``telemetry_events``."""

    def _insert(events: list[tuple]) -> None:
        with engine.begin() as connection:
            for event_id, timestamp, tags in events:
                connection.execute(
                    text(
                        "insert into telemetry_events "
                        "(event_id, timestamp, received_at, event_type, service, "
                        " session_id, user_id, schema_version, request_id, source, tags) "
                        "values (:event_id, :timestamp, :received_at, :event_type, "
                        " :service, :session_id, :user_id, :schema_version, "
                        " :request_id, :source, :tags)"
                    ),
                    {
                        "event_id": event_id,
                        "timestamp": sqlite_timestamp(timestamp),
                        "received_at": sqlite_timestamp(timestamp),
                        "event_type": "inbound_order_created",
                        "service": "backoffice",
                        "session_id": "sess-1",
                        "user_id": None,
                        "schema_version": "2.0.0",
                        "request_id": None,
                        "source": "frontend",
                        "tags": tags,
                    },
                )

    return _insert
