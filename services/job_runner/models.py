"""Modelo ORM de ``job_runs`` (ciclo de vida de los disparos programados).

La tabla es la fuente de verdad del estado de un job. El DDL canónico vive en
``services/api/migrations/0002_job_runs.sql``; este modelo lo replica para
SQLite (tests y ejecución local) y para las consultas del repositorio.

Capas distintas: ``job_runs`` describe *intentos de disparo* (cron → un intento
por día). ``reporting.pipeline_runs`` describe *ejecuciones del pipeline*
(una por semana). No se fusionan ni se referencian entre sí.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlmodel import Field, SQLModel

#: Nombre del job que ejecuta ``scripts/nightly_export.py``.
JOB_NAME_NIGHTLY_EXPORT = "nightly_export"

#: Estados permitidos por la máquina de estados.
JOB_STATUSES: tuple[str, ...] = ("pending", "processing", "completed", "failed")

#: Estados finales: no se reabren, un reintento crea una fila nueva.
TERMINAL_STATUSES: tuple[str, ...] = ("completed", "failed")

STATUS_CHECK_SQL = "status in ('pending', 'processing', 'completed', 'failed')"

#: Los mensajes de error se recortan para no inflar la tabla.
MAX_ERROR_MESSAGE_LENGTH = 2000


def utcnow() -> datetime:
    """Ahora en UTC (aware)."""

    return datetime.now(timezone.utc)


class JobRun(SQLModel, table=True):
    """Un intento de ejecución de un job para una fecha objetivo."""

    __tablename__ = "job_runs"
    __table_args__ = (
        CheckConstraint(STATUS_CHECK_SQL, name="ck_job_runs_status"),
        # Índice exigido para las consultas de idempotencia.
        Index("ix_job_runs_job_target", "job_name", "target_date"),
        # Lock: como máximo una ejecución en curso por job.
        Index(
            "ux_job_runs_processing",
            "job_name",
            unique=True,
            postgresql_where=text("status = 'processing'"),
            sqlite_where=text("status = 'processing'"),
        ),
        # Idempotencia: como máximo una ejecución completada por job y día.
        Index(
            "ux_job_runs_completed",
            "job_name",
            "target_date",
            unique=True,
            postgresql_where=text("status = 'completed'"),
            sqlite_where=text("status = 'completed'"),
        ),
        Index("ix_job_runs_status_started", "status", "started_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    job_name: str = Field(sa_column=Column(String, nullable=False))
    target_date: date = Field(sa_column=Column(Date, nullable=False))
    status: str = Field(
        default="pending",
        sa_column=Column(String, nullable=False, server_default="pending"),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    error_message: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )


def create_job_runs_table(engine) -> None:
    """Crea ``job_runs`` si no existe (SQLite local y tests).

    En PostgreSQL la tabla la crea la migración ``0002_job_runs.sql``; este
    helper es idempotente y no altera una tabla existente.
    """

    JobRun.__table__.create(engine, checkfirst=True)
