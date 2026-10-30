"""Transiciones y consultas de ``job_runs``.

Cada transición se confirma en su propia transacción: el estado debe reflejar
la realidad aunque el proceso muera justo después. Los ``UPDATE`` van guardados
por el estado de origen, de modo que la máquina de estados no se puede saltar
ni desde un bug del llamador.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from .models import (
    JOB_STATUSES,
    MAX_ERROR_MESSAGE_LENGTH,
    TERMINAL_STATUSES,
    JobRun,
    utcnow,
)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normaliza a UTC (SQLite devuelve datetimes naive)."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _truncate(message: str) -> str:
    text = " ".join(str(message).split())
    return text[:MAX_ERROR_MESSAGE_LENGTH]


def create_pending(
    session: Session, job_name: str, target_date: date
) -> JobRun:
    """Crea la fila ``pending`` *antes* de cualquier trabajo."""

    run = JobRun(
        job_name=job_name,
        target_date=target_date,
        status="pending",
        created_at=utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_run(session: Session, run_id: int) -> JobRun | None:
    return session.get(JobRun, run_id)


def mark_processing(session: Session, run_id: int) -> bool:
    """``pending`` → ``processing``. ``False`` si no se pudo (carrera o estado)."""

    try:
        result = session.execute(
            update(JobRun)
            .where(JobRun.id == run_id, JobRun.status == "pending")
            .values(status="processing", started_at=utcnow(), error_message=None)
        )
        session.commit()
    except IntegrityError:
        # El índice parcial único ya tiene un 'processing' para este job.
        session.rollback()
        return False
    return result.rowcount == 1


def mark_completed(session: Session, run_id: int) -> bool:
    """``processing`` → ``completed`` (solo tras terminar el trabajo con éxito)."""

    result = session.execute(
        update(JobRun)
        .where(JobRun.id == run_id, JobRun.status == "processing")
        .values(status="completed", finished_at=utcnow(), error_message=None)
    )
    session.commit()
    return result.rowcount == 1


def mark_failed(session: Session, run_id: int, error_message: str) -> bool:
    """``pending``/``processing`` → ``failed`` con el diagnóstico."""

    result = session.execute(
        update(JobRun)
        .where(
            JobRun.id == run_id,
            JobRun.status.in_(("pending", "processing")),
        )
        .values(
            status="failed",
            finished_at=utcnow(),
            error_message=_truncate(error_message),
        )
    )
    session.commit()
    return result.rowcount == 1


def has_processing_lock(session: Session, job_name: str) -> bool:
    """¿Hay una ejecución en curso para este job? (lock vía estado)."""

    stmt = (
        select(func.count())
        .select_from(JobRun)
        .where(JobRun.job_name == job_name, JobRun.status == "processing")
    )
    return bool(session.execute(stmt).scalar_one())


def has_completed_for_date(
    session: Session, job_name: str, target_date: date
) -> bool:
    """¿Ya se completó este job para esta fecha objetivo? (idempotencia diaria)."""

    stmt = (
        select(func.count())
        .select_from(JobRun)
        .where(
            JobRun.job_name == job_name,
            JobRun.target_date == target_date,
            JobRun.status == "completed",
        )
    )
    return bool(session.execute(stmt).scalar_one())


def reconcile_stale_processing(
    session: Session, job_name: str, max_age_minutes: int = 60
) -> list[JobRun]:
    """Convierte ``processing`` huérfanos (proceso muerto) en ``failed``.

    Sin esto, un proceso interrumpido bloquearía el job para siempre. La
    antigüedad se mide desde ``started_at`` (o ``created_at`` si faltara).
    """

    rows = session.execute(
        select(JobRun).where(
            JobRun.job_name == job_name, JobRun.status == "processing"
        )
    ).scalars().all()

    now = utcnow()
    recovered: list[JobRun] = []
    for row in rows:
        reference = _as_utc(row.started_at) or _as_utc(row.created_at)
        if reference is None:
            continue
        age = now - reference
        if age < timedelta(minutes=max_age_minutes):
            continue
        mark_failed(
            session,
            row.id,
            "stale_processing: sin actividad desde "
            f"{reference.isoformat()} (> {max_age_minutes} min)",
        )
        refreshed = session.get(JobRun, row.id)
        if refreshed is not None:
            recovered.append(refreshed)
    return recovered


def list_runs(
    session: Session, job_name: str | None = None, limit: int = 20
) -> list[JobRun]:
    """Últimas ejecuciones (diagnóstico y tests)."""

    stmt = select(JobRun)
    if job_name is not None:
        stmt = stmt.where(JobRun.job_name == job_name)
    stmt = stmt.order_by(JobRun.id.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())


__all__ = [
    "JOB_STATUSES",
    "TERMINAL_STATUSES",
    "create_pending",
    "get_run",
    "has_completed_for_date",
    "has_processing_lock",
    "list_runs",
    "mark_completed",
    "mark_failed",
    "mark_processing",
    "reconcile_stale_processing",
]
