"""Flows de Prefect del pipeline semanal.

El flow padre procesa varias semanas y **no aborta en la primera falla**: cada
``process_week`` se ejecuta como subflow con ``return_state=True`` y el padre
falla al final si alguna semana quedó mal.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from prefect import flow

from .core import WeekSteps, execute_week, resolve_target_weeks
from .db import get_engine
from .settings import DEFAULT_LOOKBACK_WEEKS, get_instrumentation_since
from .sql import create_reporting_schema
from .tasks import (
    aggregate_task,
    extract_task,
    load_task,
    normalize_task,
    quality_task,
    reconcile_source_task,
    reconcile_task,
)


def _week_steps() -> WeekSteps:
    return WeekSteps(
        extract=extract_task,
        normalize=normalize_task,
        aggregate=aggregate_task,
        quality=quality_task,
        load=load_task,
        reconcile=reconcile_task,
    )


@flow(name="process-week")
def process_week(
    week_start: date,
    *,
    triggered_by: str = "schedule",
    force: bool = False,
    reason: str | None = None,
):
    create_reporting_schema(get_engine())
    result = execute_week(
        None,
        week_start,
        triggered_by=triggered_by,
        force=force,
        reason=reason,
        instrumentation_since=get_instrumentation_since(),
        steps=_week_steps(),
    )
    if result.status == "failed":
        raise ValueError(
            f"Semana {week_start} falló: {result.error or 'error desconocido'}"
        )
    return result


@flow(name="weekly-warehouse-client-performance")
def weekly_flow(
    lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    week_start: date | None = None,
    *,
    triggered_by: str = "schedule",
    force: bool = False,
    reason: str | None = None,
):
    weeks = (
        [week_start]
        if week_start is not None
        else resolve_target_weeks(lookback_weeks)
    )
    states = [
        process_week.with_options(return_state=True)(
            week,
            triggered_by=triggered_by,
            force=force,
            reason=reason,
        )
        for week in weeks
    ]

    failed = [state for state in states if state.is_failed()]
    if failed:
        raise RuntimeError(
            f"{len(failed)} de {len(states)} semanas fallaron: "
            + ", ".join(str(state.message) for state in failed)
        )
    return [state.result() for state in states]


@flow(name="source-reconciliation")
def source_reconciliation_flow(days: int = 7):
    """Compara órdenes SQL y eventos persistidos de los últimos ``days`` días."""

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    return reconcile_source_task(start, end)
