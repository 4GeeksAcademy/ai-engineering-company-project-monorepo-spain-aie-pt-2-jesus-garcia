"""Definición portable (PostgreSQL/SQLite) de las tablas del pipeline.

Las tablas de ``reporting`` viven en un esquema dedicado en PostgreSQL. En
SQLite (solo tests) se crean sin esquema. ``telemetry_events`` es de solo
lectura y se declara aparte para no acoplar el pipeline a los modelos de la API.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB


def _json_type():
    return JSON().with_variant(JSONB(), "postgresql")


@dataclass(frozen=True)
class ReportingTables:
    metadata: MetaData
    performance: Table
    runs: Table
    steps: Table
    rejects: Table
    watermarks: Table
    published: Table
    revisions: Table


def build_reporting_tables(schema: str | None) -> ReportingTables:
    metadata = MetaData(schema=schema)

    performance = Table(
        "weekly_warehouse_client_performance",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("warehouse", String(64), nullable=False),
        Column("client_id", String(128), nullable=False),
        Column("week_start", Date, nullable=False),
        Column("inbound_units_count", Integer, nullable=False, default=0),
        Column("outbound_orders_count", Integer, nullable=False, default=0),
        Column("stockout_events_count", Integer, nullable=False, default=0),
        Column("discrepancy_events_count", Integer, nullable=False, default=0),
        Column("discrepancy_rate", Numeric(12, 6), nullable=False, default=0),
        Column("computed_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint(
            "warehouse",
            "client_id",
            "week_start",
            name="uq_weekly_performance_warehouse_client_week",
        ),
        CheckConstraint(
            "inbound_units_count >= 0", name="ck_weekly_performance_inbound"
        ),
        CheckConstraint(
            "outbound_orders_count >= 0", name="ck_weekly_performance_outbound"
        ),
        CheckConstraint(
            "stockout_events_count >= 0", name="ck_weekly_performance_stockout"
        ),
        CheckConstraint(
            "discrepancy_events_count >= 0",
            name="ck_weekly_performance_discrepancy",
        ),
        CheckConstraint(
            "discrepancy_rate >= 0 AND discrepancy_rate <= 1",
            name="ck_weekly_performance_rate",
        ),
    )
    Index(
        "ix_weekly_performance_week",
        performance.c.week_start,
    )

    runs = Table(
        "pipeline_runs",
        metadata,
        Column("run_id", String(36), primary_key=True),
        Column("pipeline_name", String(128), nullable=False),
        Column("flow_run_id", String(128)),
        Column("week_start", Date),
        Column(
            "status",
            String(16),
            nullable=False,
            server_default=text("'running'"),
        ),
        Column("triggered_by", String(64), nullable=False),
        Column("started_at", DateTime(timezone=True), nullable=False),
        Column("heartbeat_at", DateTime(timezone=True)),
        Column("finished_at", DateTime(timezone=True)),
        Column("rows_extracted", Integer, nullable=False, default=0),
        Column("rows_valid", Integer, nullable=False, default=0),
        Column("rows_rejected", Integer, nullable=False, default=0),
        Column("rows_written", Integer, nullable=False, default=0),
        Column("source_fingerprint", String(64)),
        Column("quality_status", String(16)),
        Column("error_message", String(2048)),
        Column("code_version", String(32)),
        Column("instrumentation_since", Date),
        CheckConstraint(
            "status IN ('running','success','failed','skipped')",
            name="ck_pipeline_runs_status",
        ),
    )
    Index(
        "ix_pipeline_runs_started",
        runs.c.pipeline_name,
        runs.c.started_at,
    )
    Index(
        "ux_pipeline_runs_active_week",
        runs.c.pipeline_name,
        runs.c.week_start,
        unique=True,
        postgresql_where=text("status = 'running'"),
        sqlite_where=text("status = 'running'"),
    )

    steps = Table(
        "pipeline_run_steps",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column(
            "run_id",
            String(36),
            nullable=False,
        ),
        Column("step", String(64), nullable=False),
        Column("attempt", Integer, nullable=False, default=1),
        Column(
            "status",
            String(16),
            nullable=False,
            server_default=text("'started'"),
        ),
        Column("started_at", DateTime(timezone=True), nullable=False),
        Column("finished_at", DateTime(timezone=True)),
        Column("detail", _json_type()),
        CheckConstraint(
            "status IN ('started','success','failed','skipped')",
            name="ck_pipeline_run_steps_status",
        ),
    )
    Index("ix_pipeline_run_steps_run", steps.c.run_id, steps.c.started_at)

    rejects = Table(
        "weekly_performance_rejects",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("run_id", String(36)),
        Column("event_id", String(64)),
        Column("week_start", Date),
        Column("reason", String(128), nullable=False),
        Column("payload", _json_type(), nullable=False),
        Column("replayed_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    Index("ix_weekly_performance_rejects_run", rejects.c.run_id)

    watermarks = Table(
        "week_watermarks",
        metadata,
        Column("week_start", Date, primary_key=True),
        Column("last_run_id", String(36)),
        Column("source_fingerprint", String(64), nullable=False),
        Column("rows_written", Integer, nullable=False, default=0),
        Column("computed_at", DateTime(timezone=True), nullable=False),
    )

    published = Table(
        "published_weeks",
        metadata,
        Column("week_start", Date, primary_key=True),
        Column("published_at", DateTime(timezone=True), nullable=False),
        Column("published_by", String(128), nullable=False),
        Column("frozen", Boolean, nullable=False, default=True),
    )

    revisions = Table(
        "weekly_performance_revisions",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("week_start", Date, nullable=False),
        Column("run_id", String(36), nullable=False),
        Column("reason", String(512), nullable=False),
        Column("forced_by", String(128), nullable=False),
        Column("snapshot", _json_type(), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    Index(
        "ix_weekly_performance_revisions_week",
        revisions.c.week_start,
        revisions.c.created_at,
    )

    return ReportingTables(
        metadata=metadata,
        performance=performance,
        runs=runs,
        steps=steps,
        rejects=rejects,
        watermarks=watermarks,
        published=published,
        revisions=revisions,
    )


@lru_cache(maxsize=4)
def get_reporting_tables(schema: str | None) -> ReportingTables:
    return build_reporting_tables(schema)


def telemetry_table() -> Table:
    """Vista declarativa de ``telemetry_events`` (solo las columnas usadas)."""

    metadata = MetaData()
    return Table(
        "telemetry_events",
        metadata,
        Column("event_id", String(36), primary_key=True),
        Column("timestamp", DateTime(timezone=True), nullable=False),
        Column("event_type", String(64), nullable=False),
        Column("session_id", String(128), nullable=False),
        Column("user_id", String(128)),
        Column("schema_version", String(16), nullable=False),
        Column("request_id", String(128)),
        Column("source", String(32), nullable=False),
        Column("service", String(32), nullable=False),
        Column("tags", _json_type(), nullable=False),
        Column("received_at", DateTime(timezone=True), nullable=False),
    )


def outbox_table(schema: str | None) -> Table:
    """Outbox transaccional (se usará en la fase de instrumentación de origen)."""

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
