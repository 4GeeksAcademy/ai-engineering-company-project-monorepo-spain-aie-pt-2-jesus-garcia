"""Tasks de Prefect: envoltorios finos sobre la lógica de ``core``.

Cada task abre su propio engine para que Prefect no tenga que serializar
conexiones entre procesos. Los reintentos solo cubren errores transitorios
(conexión/timeout); la validación y los quality gates no reintentan.
"""

from __future__ import annotations

from datetime import date

from prefect import task
from sqlalchemy.exc import DBAPIError, OperationalError

from pipelines.weekly_performance.core import (
    NormalizeResult,
    QualityReport,
    aggregate_kpis,
    evaluate_quality,
    extract_week,
    load_week,
    normalize_validate,
    reconcile_source,
    reconcile_week,
)
from pipelines.weekly_performance.db import get_engine


def _is_transient(_task, _task_run, state) -> bool:
    """Solo reintenta fallos de conexión/timeout, nunca datos inválidos."""

    exc = getattr(state, "data", None)
    if isinstance(exc, OperationalError):
        return True
    if isinstance(exc, DBAPIError):
        return bool(getattr(exc, "connection_invalidated", False))
    return isinstance(exc, (TimeoutError, ConnectionError))


@task(
    name="extract-week",
    retries=3,
    retry_delay_seconds=[30, 120, 300],
    retry_jitter_factor=0.1,
    retry_condition_fn=_is_transient,
)
def extract_task(week_start: date) -> list[dict]:
    return extract_week(get_engine(), week_start)


@task(name="normalize-validate")
def normalize_task(rows: list[dict], week_start: date) -> NormalizeResult:
    return normalize_validate(rows, week_start)


@task(name="aggregate-kpis")
def aggregate_task(valid_rows: list[dict]) -> list[dict]:
    return aggregate_kpis(valid_rows)


@task(name="quality-gates")
def quality_task(
    kpis: list[dict],
    *,
    rejects: int,
    total_rows: int,
    week_start: date,
    duplicate_order_ids: int = 0,
    instrumentation_since: date | None = None,
    previous_kpis: list[dict] | None = None,
    source_freshness_hours: float | None = None,
) -> QualityReport:
    return evaluate_quality(
        kpis,
        rejects=rejects,
        total_rows=total_rows,
        week_start=week_start,
        duplicate_order_ids=duplicate_order_ids,
        instrumentation_since=instrumentation_since,
        previous_kpis=previous_kpis,
        source_freshness_hours=source_freshness_hours,
    )


@task(
    name="load-week",
    retries=2,
    retry_delay_seconds=[15, 60],
    retry_condition_fn=_is_transient,
)
def load_task(kpis: list[dict], week_start: date, run_id: str) -> int:
    return load_week(get_engine(), kpis, week_start, run_id)


@task(
    name="reconcile-week",
    retries=2,
    retry_delay_seconds=[15, 60],
    retry_condition_fn=_is_transient,
)
def reconcile_task(kpis: list[dict], week_start: date) -> int:
    return reconcile_week(get_engine(), kpis, week_start)


@task(name="reconcile-source", retries=2, retry_delay_seconds=[30, 120])
def reconcile_source_task(start_date: date, end_date: date) -> list[dict]:
    return reconcile_source(get_engine(), start_date, end_date)
