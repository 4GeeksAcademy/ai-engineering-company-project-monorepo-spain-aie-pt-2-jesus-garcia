"""Consultas de solo lectura sobre las tablas ``reporting.*``."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import text
from sqlmodel import Session

from .schemas import (
    PipelineRunLatest,
    WeeklyPerformanceEntry,
    WeeklyPerformanceResponse,
)


class ReportNotFound(Exception):
    """No hay datos para la semana solicitada."""


def _prefix(session: Session) -> str:
    bind = session.get_bind()
    return "" if bind is not None and bind.dialect.name == "sqlite" else "reporting."


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_datetime(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def get_weekly_performance(
    session: Session,
    week_start: date | None = None,
) -> WeeklyPerformanceResponse:
    prefix = _prefix(session)
    table = f"{prefix}weekly_warehouse_client_performance"

    if week_start is None:
        row = session.execute(text(f"select max(week_start) from {table}")).first()
        if row is None or row[0] is None:
            raise ReportNotFound("No hay semanas calculadas.")
        week_start = _as_date(row[0])

    rows = session.execute(
        text(
            f"""
            select warehouse, client_id, inbound_units_count, outbound_orders_count,
                   stockout_events_count, discrepancy_events_count, discrepancy_rate,
                   computed_at
            from {table}
            where week_start = :week
            order by warehouse, client_id
            """
        ),
        {"week": week_start},
    ).mappings().all()

    if not rows:
        raise ReportNotFound(f"No hay datos para la semana {week_start}.")

    frozen = bool(
        session.execute(
            text(
                f"select frozen from {prefix}published_weeks "
                "where week_start = :week"
            ),
            {"week": week_start},
        ).scalar()
    )
    latest_status = session.execute(
        text(
            f"select status from {prefix}pipeline_runs "
            "where week_start = :week order by started_at desc limit 1"
        ),
        {"week": week_start},
    ).scalar()
    stale = latest_status in {"failed", "running"}

    entries = [
        WeeklyPerformanceEntry(
            warehouse=row["warehouse"],
            client_id=row["client_id"],
            inbound_units_count=int(row["inbound_units_count"]),
            outbound_orders_count=int(row["outbound_orders_count"]),
            stockout_events_count=int(row["stockout_events_count"]),
            discrepancy_events_count=int(row["discrepancy_events_count"]),
            discrepancy_rate=float(row["discrepancy_rate"]),
        )
        for row in rows
    ]
    computed_at = max(
        (_as_datetime(row["computed_at"]) for row in rows),
        default=None,
    )
    return WeeklyPerformanceResponse(
        week_start=week_start,
        entries=entries,
        frozen=frozen,
        stale=stale,
        computed_at=computed_at,
    )


def get_latest_pipeline_run(session: Session) -> PipelineRunLatest:
    prefix = _prefix(session)
    row = session.execute(
        text(
            f"""
            select run_id, status, week_start, started_at, finished_at,
                   rows_extracted, rows_valid, rows_rejected, rows_written,
                   quality_status, error_message, source_fingerprint,
                   instrumentation_since
            from {prefix}pipeline_runs
            order by started_at desc
            limit 1
            """
        )
    ).mappings().first()

    if row is None:
        raise ReportNotFound("No hay corridas registradas.")

    payload = dict(row)
    payload["week_start"] = _as_date(payload.get("week_start"))
    payload["started_at"] = _as_datetime(payload.get("started_at"))
    payload["finished_at"] = _as_datetime(payload.get("finished_at"))
    payload["instrumentation_since"] = _as_date(
        payload.get("instrumentation_since")
    )
    payload["stale"] = payload["status"] != "success"
    return PipelineRunLatest(**payload)


def has_running_run(session: Session, week_start: date | None = None) -> bool:
    prefix = _prefix(session)
    query = f"select 1 from {prefix}pipeline_runs where status = 'running'"
    params: dict = {}
    if week_start is not None:
        query += " and week_start = :week"
        params["week"] = week_start
    return session.execute(text(query), params).first() is not None
