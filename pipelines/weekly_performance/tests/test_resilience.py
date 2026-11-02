from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select

from pipelines.weekly_performance import core
from pipelines.weekly_performance.core import (
    freeze_week,
    mark_zombie_runs,
    maybe_freeze_week,
    replay_rejects,
    run_week,
    source_is_tripped,
)
from pipelines.weekly_performance.locks import advisory_key, week_lock
from pipelines.weekly_performance.settings import PIPELINE_NAME
from pipelines.weekly_performance.sql import tables_for
from pipelines.weekly_performance.tests.factories import WEEKS

W1 = WEEKS[0]
W2 = WEEKS[1]


def _insert_run(
    engine,
    run_id: str,
    *,
    week_start=W1,
    status: str = "failed",
    started_at: datetime | None = None,
    error_message: str | None = None,
):
    tables = tables_for(engine)
    started_at = started_at or datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.runs).values(
                run_id=run_id,
                pipeline_name=PIPELINE_NAME,
                week_start=week_start,
                status=status,
                triggered_by="test",
                started_at=started_at,
                heartbeat_at=started_at,
                finished_at=started_at,
                error_message=error_message,
            )
        )


def _insert_step(engine, run_id: str, step: str, status: str):
    tables = tables_for(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.steps).values(
                run_id=run_id,
                step=step,
                status=status,
                started_at=now,
                finished_at=now,
            )
        )


def _seed_extract_failures(engine, count: int = 3):
    now = datetime.now(timezone.utc)
    for index in range(count):
        run_id = f"failed-extract-{index}"
        _insert_run(
            engine,
            run_id,
            started_at=now - timedelta(minutes=10 - index),
            error_message="connection reset",
        )
        _insert_step(engine, run_id, "extract", "failed")


def test_advisory_key_is_stable_and_week_specific():
    assert advisory_key(W1) == advisory_key(W1)
    assert advisory_key(W1) != advisory_key(W2)


def test_week_lock_is_noop_on_sqlite(engine):
    with week_lock(engine, W1) as acquired:
        assert acquired is True


def test_watchdog_marks_stale_running_runs(engine):
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    _insert_run(engine, "zombie", status="running", started_at=old)

    assert mark_zombie_runs(engine) == 1

    tables = tables_for(engine)
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.runs).where(tables.runs.c.run_id == "zombie")
        ).mappings().one()
    assert row["status"] == "failed"
    assert "watchdog" in row["error_message"]


def test_watchdog_keeps_fresh_runs(engine):
    _insert_run(engine, "fresh", status="running")
    assert mark_zombie_runs(engine) == 0


def test_source_is_tripped_after_three_extract_failures(engine):
    _seed_extract_failures(engine)
    assert source_is_tripped(engine) is True

    _insert_run(engine, "success-after", status="success")
    assert source_is_tripped(engine) is False


def test_circuit_breaker_stays_open_after_blocked_runs(engine, seeded):
    _seed_extract_failures(engine)

    for _ in range(3):
        result = run_week(engine, W1, triggered_by="test")
        assert result.error == "source_unavailable"

    assert source_is_tripped(engine) is True


def test_circuit_breaker_blocks_and_force_bypasses(engine, seeded):
    _seed_extract_failures(engine)

    blocked = run_week(engine, W1, triggered_by="test")
    assert blocked.status == "failed"
    assert blocked.error == "source_unavailable"

    forced = run_week(engine, W1, triggered_by="test", force=True)
    assert forced.status == "success"


def test_force_on_frozen_week_writes_revision(engine, seeded):
    run_week(engine, W1, triggered_by="test")
    freeze_week(engine, W1, published_by="test")

    result = run_week(
        engine,
        W1,
        triggered_by="test",
        force=True,
        reason="corrección manual",
    )

    assert result.status == "success"
    tables = tables_for(engine)
    with engine.connect() as conn:
        revisions = conn.execute(select(tables.revisions)).mappings().all()
    assert len(revisions) == 1
    assert len(revisions[0]["snapshot"]) == 2
    assert revisions[0]["reason"] == "corrección manual"


def test_maybe_freeze_after_two_successful_runs(engine, seeded):
    run_week(engine, W1, triggered_by="test")
    run_week(engine, W1, triggered_by="test", force=True)

    tables = tables_for(engine)
    with engine.connect() as conn:
        published = conn.execute(
            select(tables.published).where(tables.published.c.week_start == W1)
        ).first()
    assert published is not None
    assert published.frozen is True

    third = run_week(engine, W1, triggered_by="test")
    assert third.status == "skipped"
    assert third.skipped_reason == "frozen"


def test_replay_rejects_marks_them_replayed(engine, seeded):
    first = run_week(engine, W2, triggered_by="test")
    assert first.rows_rejected == 2

    result = replay_rejects(engine, first.run_id)

    assert result.status == "success"
    tables = tables_for(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.rejects.c.replayed_at).where(
                tables.rejects.c.run_id == first.run_id
            )
        ).scalars().all()
    assert len(rows) == 2
    assert all(value is not None for value in rows)


def test_locked_week_returns_skipped(engine, seeded, monkeypatch):
    @contextmanager
    def _locked(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(core, "week_lock", _locked)

    result = run_week(engine, W1, triggered_by="test")
    assert result.status == "skipped"
    assert result.skipped_reason == "locked"
