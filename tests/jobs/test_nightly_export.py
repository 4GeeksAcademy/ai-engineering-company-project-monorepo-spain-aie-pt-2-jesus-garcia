"""Tests del script ``scripts/nightly_export.py`` (ciclo de vida completo)."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
import logging
from pathlib import Path
import re
import subprocess

import pytest
from sqlalchemy import func, select, update
from sqlmodel import Session

import scripts.nightly_export as nightly
from services.job_runner.logs import LOG_FORMAT, UTCFormatter
from services.job_runner.models import (
    JOB_NAME_NIGHTLY_EXPORT,
    JobRun,
    create_job_runs_table,
    utcnow,
)
from services.job_runner.repository import (
    create_pending,
    mark_completed,
    mark_failed,
    mark_processing,
)

JOB = JOB_NAME_NIGHTLY_EXPORT
DAY = date(2026, 10, 29)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def runs(engine) -> list[JobRun]:
    with Session(engine) as session:
        return list(
            session.execute(select(JobRun).order_by(JobRun.id)).scalars().all()
        )


def processing_count(engine) -> int:
    with Session(engine) as session:
        return session.execute(
            select(func.count())
            .select_from(JobRun)
            .where(JobRun.status == "processing")
        ).scalar_one()


def ok_export(rows: int = 3, path: Path | None = None):
    def _export(session, target_date, output_dir):
        return nightly.ExportResult(
            path=path or Path(output_dir) / "telemetry.csv",
            rows=rows,
            skipped=False,
        )

    return _export


def explode(*_args, **_kwargs):
    raise AssertionError("no debería ejecutarse")


def completed_run(engine, target_date=DAY) -> int:
    with Session(engine) as session:
        run = create_pending(session, JOB, target_date)
        mark_processing(session, run.id)
        mark_completed(session, run.id)
        return run.id


# --------------------------------------------------------------------------- #
# Camino feliz
# --------------------------------------------------------------------------- #


def test_happy_path_completes_after_export_and_pipeline(engine, tmp_path):
    calls: list[str] = []

    def export_fn(session, target_date, output_dir):
        calls.append("export")
        return nightly.ExportResult(
            path=tmp_path / "telemetry.csv", rows=4, skipped=False
        )

    def pipeline_fn():
        calls.append("pipeline")
        return 0

    assert (
        nightly.run(
            DAY,
            engine=engine,
            export_fn=export_fn,
            pipeline_fn=pipeline_fn,
            output_dir=tmp_path,
        )
        == nightly.EXIT_OK
    )
    assert calls == ["export", "pipeline"]

    stored = runs(engine)
    assert len(stored) == 1
    row = stored[0]
    assert row.status == "completed"
    assert row.target_date == DAY
    assert row.started_at is not None
    assert row.finished_at is not None
    assert row.error_message is None


def test_processing_is_persisted_before_any_work(engine, tmp_path):
    observed: dict[str, object] = {}

    def export_fn(session, target_date, output_dir):
        # Otra conexión: solo ve lo que está confirmado.
        with Session(engine) as probe:
            row = probe.execute(select(JobRun)).scalars().one()
            observed["status"] = row.status
            observed["started_at"] = row.started_at
        return nightly.ExportResult(path=tmp_path / "x.csv", rows=0, skipped=False)

    nightly.run(
        DAY,
        engine=engine,
        export_fn=export_fn,
        pipeline_fn=lambda: 0,
        output_dir=tmp_path,
    )

    assert observed["status"] == "processing"
    assert observed["started_at"] is not None


def test_pipeline_failure_marks_failed_and_leaves_no_processing(engine, tmp_path):
    def pipeline_fn():
        raise nightly.PipelineError("rc=1 stderr=quality gate failed")

    code = nightly.run(
        DAY,
        engine=engine,
        export_fn=ok_export(),
        pipeline_fn=pipeline_fn,
        output_dir=tmp_path,
    )

    assert code == nightly.EXIT_FAILED
    row = runs(engine)[0]
    assert row.status == "failed"
    assert "PipelineError" in row.error_message
    assert "quality gate failed" in row.error_message
    assert row.finished_at is not None
    assert processing_count(engine) == 0


def test_export_exception_marks_failed(engine, tmp_path):
    def export_fn(session, target_date, output_dir):
        raise nightly.ExportError("telemetry_events no existe")

    code = nightly.run(
        DAY,
        engine=engine,
        export_fn=export_fn,
        pipeline_fn=explode,
        output_dir=tmp_path,
    )

    assert code == nightly.EXIT_FAILED
    row = runs(engine)[0]
    assert row.status == "failed"
    assert "telemetry_events no existe" in row.error_message
    assert processing_count(engine) == 0


def test_unexpected_exception_is_captured(engine, tmp_path):
    def pipeline_fn():
        raise RuntimeError("unexpected")

    code = nightly.run(
        DAY,
        engine=engine,
        export_fn=ok_export(),
        pipeline_fn=pipeline_fn,
        output_dir=tmp_path,
    )

    assert code == nightly.EXIT_FAILED
    assert "RuntimeError: unexpected" in runs(engine)[0].error_message


def test_pipeline_nonzero_returncode_marks_failed(engine, tmp_path):
    code = nightly.run(
        DAY,
        engine=engine,
        export_fn=ok_export(),
        pipeline_fn=lambda: 2,
        output_dir=tmp_path,
    )

    assert code == nightly.EXIT_FAILED
    assert "pipeline rc=2" in runs(engine)[0].error_message


# --------------------------------------------------------------------------- #
# Lock e idempotencia
# --------------------------------------------------------------------------- #


def test_processing_lock_blocks_without_new_row(engine, tmp_path, caplog):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        assert mark_processing(session, run.id) is True

    caplog.set_level(logging.INFO)
    code = nightly.run(
        DAY + timedelta(days=1),
        engine=engine,
        export_fn=explode,
        pipeline_fn=explode,
        output_dir=tmp_path,
    )

    assert code == nightly.EXIT_OK
    assert len(runs(engine)) == 1
    assert any("status=blocked" in record.getMessage() for record in caplog.records)


def test_completed_date_is_skipped(engine, tmp_path, caplog):
    completed_run(engine)

    caplog.set_level(logging.INFO)
    code = nightly.run(
        DAY,
        engine=engine,
        export_fn=explode,
        pipeline_fn=explode,
        output_dir=tmp_path,
    )

    assert code == nightly.EXIT_OK
    assert len(runs(engine)) == 1
    assert any(
        "status=skipped" in record.getMessage() for record in caplog.records
    )


def test_other_date_still_runs(engine, tmp_path):
    completed_run(engine, DAY)

    code = nightly.run(
        DAY + timedelta(days=1),
        engine=engine,
        export_fn=ok_export(),
        pipeline_fn=lambda: 0,
        output_dir=tmp_path,
    )

    assert code == nightly.EXIT_OK
    statuses = [row.status for row in runs(engine)]
    assert statuses == ["completed", "completed"]


def test_failed_date_can_be_retried(engine, tmp_path):
    with Session(engine) as session:
        run = create_pending(session, JOB, DAY)
        mark_processing(session, run.id)
        mark_failed(session, run.id, "previous failure")

    code = nightly.run(
        DAY,
        engine=engine,
        export_fn=ok_export(),
        pipeline_fn=lambda: 0,
        output_dir=tmp_path,
    )

    assert code == nightly.EXIT_OK
    statuses = [row.status for row in runs(engine)]
    assert statuses == ["failed", "completed"]


def test_stale_processing_is_recovered_then_run_proceeds(engine, tmp_path, caplog):
    with Session(engine) as session:
        stale = create_pending(session, JOB, DAY - timedelta(days=1))
        mark_processing(session, stale.id)
        session.execute(
            update(JobRun)
            .where(JobRun.id == stale.id)
            .values(started_at=utcnow() - timedelta(hours=3))
        )
        session.commit()

    caplog.set_level(logging.INFO)
    code = nightly.run(
        DAY,
        engine=engine,
        export_fn=ok_export(),
        pipeline_fn=lambda: 0,
        output_dir=tmp_path,
        stale_age_minutes=60,
    )

    assert code == nightly.EXIT_OK
    rows = runs(engine)
    assert [row.status for row in rows] == ["failed", "completed"]
    assert "stale_processing" in rows[0].error_message
    assert any(
        "processing huérfano reconciliado" in record.getMessage()
        for record in caplog.records
    )


# --------------------------------------------------------------------------- #
# Exportación CSV
# --------------------------------------------------------------------------- #


def test_export_day_writes_only_target_date(engine, tmp_path, insert_events):
    insert_events(
        [
            (
                "e1",
                datetime(2026, 10, 29, 0, 0, 5, tzinfo=timezone.utc),
                '{"order_id": "a"}',
            ),
            (
                "e2",
                datetime(2026, 10, 29, 23, 59, 59, tzinfo=timezone.utc),
                None,
            ),
            (
                "e3",
                datetime(2026, 10, 30, 0, 0, 0, tzinfo=timezone.utc),
                '{"order_id": "c"}',
            ),
        ],
    )

    with Session(engine) as session:
        result = nightly.export_day(session, DAY, tmp_path)

    assert result.skipped is False
    assert result.rows == 2
    assert result.path.name == f"telemetry_{DAY.isoformat()}.csv"

    rows = list(csv.reader(io.StringIO(result.path.read_text(encoding="utf-8"))))
    assert rows[0] == list(nightly.CSV_COLUMNS)
    assert [row[0] for row in rows[1:]] == ["e1", "e2"]
    assert json.loads(rows[1][-1]) == {"order_id": "a"}
    assert rows[2][-1] == ""


def test_export_day_writes_header_for_empty_day(engine, tmp_path):
    with Session(engine) as session:
        result = nightly.export_day(session, DAY, tmp_path)

    assert result.rows == 0
    lines = result.path.read_text(encoding="utf-8").splitlines()
    assert lines == [",".join(nightly.CSV_COLUMNS)]


def test_existing_csv_is_not_overwritten(engine, tmp_path, insert_events):
    path = tmp_path / f"telemetry_{DAY.isoformat()}.csv"
    path.write_text("sentinel\n", encoding="utf-8")
    insert_events(
        [("e1", datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc), None)],
    )

    with Session(engine) as session:
        result = nightly.export_day(session, DAY, tmp_path)

    assert result.skipped is True
    assert result.rows is None
    assert path.read_text(encoding="utf-8") == "sentinel\n"


def test_run_continues_with_pipeline_when_csv_exists(engine, tmp_path, caplog):
    (tmp_path / f"telemetry_{DAY.isoformat()}.csv").write_text(
        "sentinel\n", encoding="utf-8"
    )
    pipeline_calls: list[int] = []

    caplog.set_level(logging.INFO)
    code = nightly.run(
        DAY,
        engine=engine,
        pipeline_fn=lambda: pipeline_calls.append(1) or 0,
        output_dir=tmp_path,
    )

    assert code == nightly.EXIT_OK
    assert pipeline_calls == [1]
    assert runs(engine)[0].status == "completed"
    assert any(
        "csv existente" in record.getMessage() for record in caplog.records
    )


def test_export_failure_on_missing_table_is_wrapped(engine, tmp_path):
    from sqlalchemy import text as sql_text

    with engine.begin() as connection:
        connection.execute(sql_text("drop table telemetry_events"))

    with Session(engine) as session:
        with pytest.raises(nightly.ExportError, match="telemetry_events"):
            nightly.export_day(session, DAY, tmp_path)


# --------------------------------------------------------------------------- #
# Pipeline como subproceso
# --------------------------------------------------------------------------- #


def test_run_pipeline_wraps_nonzero(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, returncode=1, stdout="", stderr="quality gate failed"
        )

    monkeypatch.setattr(nightly.subprocess, "run", fake_run)

    with pytest.raises(nightly.PipelineError, match="rc=1"):
        nightly.run_pipeline(timeout=5)


def test_run_pipeline_wraps_timeout(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 5, stderr="still running")

    monkeypatch.setattr(nightly.subprocess, "run", fake_run)

    with pytest.raises(nightly.PipelineError, match="timeout tras 5s"):
        nightly.run_pipeline(timeout=5)


def test_run_pipeline_wraps_launch_error(monkeypatch):
    def fake_run(command, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(nightly.subprocess, "run", fake_run)

    with pytest.raises(nightly.PipelineError, match="no se pudo lanzar"):
        nightly.run_pipeline(timeout=5)


def test_error_summary_prefers_the_exception_line():
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "engine.py", line 630, in connect\n'
        "sqlalchemy.exc.OperationalError: connection refused\n"
    )
    assert (
        nightly._error_summary(stderr, "")
        == "sqlalchemy.exc.OperationalError: connection refused"
    )


def test_error_summary_falls_back_to_tail():
    assert nightly._error_summary("linea suelta", "") == "linea suelta"


# --------------------------------------------------------------------------- #
# target_date y CLI
# --------------------------------------------------------------------------- #


def test_resolve_target_date_defaults_to_yesterday_utc(monkeypatch):
    monkeypatch.delenv("TARGET_DATE", raising=False)
    expected = datetime.now(timezone.utc).date() - timedelta(days=1)
    assert nightly.resolve_target_date() == expected


def test_resolve_target_date_reads_env(monkeypatch):
    monkeypatch.setenv("TARGET_DATE", DAY.isoformat())
    assert nightly.resolve_target_date() == DAY


def test_invalid_target_date_raises_config_error(monkeypatch):
    monkeypatch.setenv("TARGET_DATE", "29/10/2026")
    with pytest.raises(nightly.ConfigError, match="TARGET_DATE"):
        nightly.resolve_target_date()


def test_main_returns_config_error_for_invalid_env(monkeypatch, caplog):
    monkeypatch.setenv("TARGET_DATE", "nope")
    caplog.set_level(logging.INFO)
    assert nightly.main([]) == nightly.EXIT_CONFIG


def test_main_rejects_invalid_cli_date():
    with pytest.raises(SystemExit) as excinfo:
        nightly.main(["--target-date", "2026-13-01"])
    assert excinfo.value.code == 2


def test_main_dry_run_writes_nothing(engine, monkeypatch, capsys):
    monkeypatch.setenv("TARGET_DATE", DAY.isoformat())
    monkeypatch.setenv("DATABASE_URL", "sqlite:///no-deberia-usarse.db")

    assert nightly.main(["--dry-run"]) == nightly.EXIT_OK
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") :])
    assert payload["target_date"] == DAY.isoformat()
    assert payload["dry_run"] is True
    assert payload["pipeline"].endswith("run --lookback 1 --json")


def test_main_runs_against_env_database(engine, monkeypatch, tmp_path):
    monkeypatch.setenv("TARGET_DATE", DAY.isoformat())
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'main.db'}")

    from sqlalchemy import create_engine

    create_job_runs_table(create_engine(f"sqlite:///{tmp_path / 'main.db'}"))

    assert nightly.main(["--reconcile-only"]) == nightly.EXIT_OK


# --------------------------------------------------------------------------- #
# Observabilidad
# --------------------------------------------------------------------------- #


def test_every_log_line_has_timestamp_job_and_status(engine, tmp_path, caplog):
    caplog.set_level(logging.INFO)

    nightly.run(
        DAY,
        engine=engine,
        export_fn=ok_export(),
        pipeline_fn=lambda: 0,
        output_dir=tmp_path,
    )

    assert caplog.records
    formatter = UTCFormatter(LOG_FORMAT)
    for record in caplog.records:
        line = formatter.format(record)
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z ", line)
        assert "job=nightly_export" in line
        assert re.search(
            r"status=(pending|processing|completed|failed|blocked|skipped)", line
        )


def test_failure_logs_at_error_level(engine, tmp_path, caplog):
    caplog.set_level(logging.INFO)

    nightly.run(
        DAY,
        engine=engine,
        export_fn=ok_export(),
        pipeline_fn=lambda: 1,
        output_dir=tmp_path,
    )

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors
    assert "status=failed" in errors[0].getMessage()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
