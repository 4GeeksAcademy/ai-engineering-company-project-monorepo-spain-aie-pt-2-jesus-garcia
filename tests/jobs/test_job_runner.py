"""Tests de la máquina de estados de ``job_runs`` (repositorio)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlmodel import Session

from services.job_runner.models import (
    JOB_NAME_NIGHTLY_EXPORT,
    JobRun,
    utcnow,
)
from services.job_runner.repository import (
    create_pending,
    get_run,
    has_completed_for_date,
    has_processing_lock,
    list_runs,
    mark_completed,
    mark_failed,
    mark_processing,
    reconcile_stale_processing,
)

JOB = JOB_NAME_NIGHTLY_EXPORT
DAY = date(2026, 10, 29)


def test_create_pending_persists_before_any_work(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        assert run.id is not None
        assert run.status == "pending"
        assert run.target_date == DAY
        assert run.started_at is None
        assert run.finished_at is None
        assert run.created_at is not None

    with Session(engine) as session:
        stored = session.get(JobRun, run.id)
        assert stored is not None and stored.status == "pending"


def test_full_lifecycle_sets_timestamps(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        assert mark_processing(session, run.id) is True
        processing = get_run(session, run.id)
        assert processing.status == "processing"
        assert processing.started_at is not None
        assert processing.finished_at is None

        assert mark_completed(session, run.id) is True
        completed = get_run(session, run.id)
        assert completed.status == "completed"
        assert completed.finished_at is not None
        assert completed.error_message is None


def test_mark_processing_only_from_pending(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        mark_processing(session, run.id)
        # Ya está en processing: una segunda transición no es válida.
        assert mark_processing(session, run.id) is False
        assert get_run(session, run.id).status == "processing"


def test_mark_completed_only_from_processing(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        assert mark_completed(session, run.id) is False
        assert get_run(session, run.id).status == "pending"


def test_mark_failed_from_pending_and_processing(engine):
    with Session(engine) as session:
        pending = create_pending(session, JOB, DAY)
        assert mark_failed(session, pending.id, "boom") is True
        failed = get_run(session, pending.id)
        assert failed.status == "failed"
        assert failed.error_message == "boom"
        assert failed.finished_at is not None

        processing = create_pending(session, JOB, DAY + timedelta(days=1))
        mark_processing(session, processing.id)
        assert mark_failed(session, processing.id, "boom 2") is True
        assert get_run(session, processing.id).status == "failed"


def test_terminal_states_are_final(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        mark_processing(session, run.id)
        mark_completed(session, run.id)
        # Ni failed ni completed pueden reabrir una fila terminada.
        assert mark_failed(session, run.id, "late") is False
        assert mark_completed(session, run.id) is False
        stored = get_run(session, run.id)
        assert stored.status == "completed"
        assert stored.error_message is None


def test_error_message_is_truncated(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        mark_failed(session, run.id, "x" * 5000)
        assert len(get_run(session, run.id).error_message) == 2000


def test_has_processing_lock(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        assert has_processing_lock(session, JOB) is False
        mark_processing(session, run.id)
        assert has_processing_lock(session, JOB) is True
        mark_completed(session, run.id)
        assert has_processing_lock(session, JOB) is False


def test_has_completed_for_date_is_scoped_by_job_and_date(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        mark_processing(session, run.id)
        mark_completed(session, run.id)

        assert has_completed_for_date(session, JOB, DAY) is True
        assert has_completed_for_date(session, JOB, DAY + timedelta(days=1)) is False
        assert has_completed_for_date(session, "otro_job", DAY) is False


def test_failed_run_does_not_block_idempotency(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        mark_processing(session, run.id)
        mark_failed(session, run.id, "boom")
        # Un fallo no marca el día como hecho: se puede reintentar.
        assert has_completed_for_date(session, JOB, DAY) is False


def test_partial_unique_index_blocks_second_processing(engine):
    with Session(engine) as session:
        first = create_pending(session, JOB, DAY)
        second = create_pending(session, JOB, DAY + timedelta(days=1))
        assert mark_processing(session, first.id) is True
        # El índice parcial único rechaza el segundo 'processing'.
        assert mark_processing(session, second.id) is False
        assert get_run(session, second.id).status == "pending"
        count = session.execute(
            select(func.count())
            .select_from(JobRun)
            .where(JobRun.status == "processing")
        ).scalar_one()
        assert count == 1


def test_reconcile_stale_processing_marks_old_rows_failed(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        mark_processing(session, run.id)
        session.execute(
            update(JobRun)
            .where(JobRun.id == run.id)
            .values(started_at=utcnow() - timedelta(hours=3))
        )
        session.commit()

        recovered = reconcile_stale_processing(session, JOB, max_age_minutes=60)
        assert [row.id for row in recovered] == [run.id]
        stored = get_run(session, run.id)
        assert stored.status == "failed"
        assert "stale_processing" in stored.error_message
        assert has_processing_lock(session, JOB) is False


def test_reconcile_keeps_fresh_processing(engine):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        mark_processing(session, run.id)

        assert reconcile_stale_processing(session, JOB, max_age_minutes=60) == []
        assert get_run(session, run.id).status == "processing"


def test_list_runs_returns_latest_first(engine):
    with Session(engine) as session:
        first = create_pending(session, JOB, DAY)
        second = create_pending(session, JOB, DAY + timedelta(days=1))
        ids = [run.id for run in list_runs(session, JOB)]
        assert ids == [second.id, first.id]


def test_create_table_is_idempotent(engine):
    from services.job_runner.models import create_job_runs_table

    create_job_runs_table(engine)
    create_job_runs_table(engine)

    with Session(engine) as session:
        assert create_pending(session, JOB, DAY).id is not None


def test_migration_declares_required_schema():
    """Contrato del DDL canónico (checklist del brief)."""

    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "api"
        / "migrations"
        / "0002_job_runs.sql"
    ).read_text(encoding="utf-8").lower()

    assert "create table if not exists public.job_runs" in sql
    for column in (
        "job_name",
        "target_date",
        "status",
        "started_at",
        "finished_at",
        "error_message",
        "created_at",
    ):
        assert column in sql
    assert "check (status in ('pending', 'processing', 'completed', 'failed'))" in sql
    assert "ix_job_runs_job_target" in sql
    assert "on public.job_runs (job_name, target_date)" in sql
    # Lock e idempotencia reforzados en la BD.
    assert "ux_job_runs_processing" in sql
    assert "ux_job_runs_completed" in sql


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
