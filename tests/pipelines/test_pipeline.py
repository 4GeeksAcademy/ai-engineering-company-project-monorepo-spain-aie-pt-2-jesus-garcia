"""Tests del entrypoint de entrega ``data/pipelines/pipeline.py``.

Cubren el contrato público (flows y CLI), el bootstrap de ``sys.path`` para
poder ejecutarlo como script y la garantía de que cada semana se procesa como
subflow aislado, sin que una falla aborte el resto.
"""

from __future__ import annotations

from datetime import date
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine

from pipelines.weekly_performance.db import clear_engine_cache
from pipelines.weekly_performance.schema import get_reporting_tables
from pipelines.weekly_performance.sql import (
    create_inventory_tables,
    create_reporting_schema,
    create_telemetry_table,
)
from pipelines.weekly_performance.tests.factories import (
    EXPECTED,
    WEEKS,
    seed_three_weeks,
)

ENTRYPOINT = Path(__file__).resolve().parents[2] / "data" / "pipelines" / "pipeline.py"


def _load_entrypoint() -> Any:
    """Carga ``pipeline.py`` por ruta, como lo haría ``python pipeline.py``."""

    spec = importlib.util.spec_from_file_location("pipeline_entrypoint", ENTRYPOINT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeState:
    def __init__(self, *, ok: bool = True, value: Any = None) -> None:
        self._ok = ok
        self._value = value

    def is_failed(self) -> bool:
        return not self._ok

    def result(self) -> Any:
        return self._value

    @property
    def message(self) -> str:
        return "fallo simulado"


class _FakeSubflow:
    """Sustituye a ``process_week`` registrando cada invocación."""

    def __init__(self, states: list[_FakeState]) -> None:
        self._states = list(states)
        self.calls: list[tuple[date, dict[str, Any]]] = []

    def with_options(self, **kwargs: Any) -> "_FakeSubflow":
        assert kwargs == {"return_state": True}
        return self

    def __call__(self, week_start: date, **kwargs: Any) -> _FakeState:
        self.calls.append((week_start, kwargs))
        return self._states.pop(0)


@pytest.fixture()
def sqlite_engine(tmp_path: Path) -> Engine:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'reporting.db'}",
        connect_args={"check_same_thread": False},
    )
    create_reporting_schema(engine)
    create_telemetry_table(engine)
    create_inventory_tables(engine)
    seed_three_weeks(engine)
    yield engine
    engine.dispose()
    clear_engine_cache()


def test_entrypoint_exposes_flows_and_cli_contract() -> None:
    module = _load_entrypoint()

    assert module.__all__ == [
        "main",
        "process_week",
        "source_reconciliation_flow",
        "weekly_flow",
    ]
    assert callable(module.main)
    assert module.weekly_flow.name == "weekly-warehouse-client-performance"
    assert module.process_week.name == "process-week"
    assert module.source_reconciliation_flow.name == "source-reconciliation"


def test_entrypoint_bootstraps_sys_path_from_any_cwd(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    for command in ("run", "backfill", "reconcile-source"):
        assert command in result.stdout


def test_entrypoint_dry_run_does_not_need_a_database(capsys) -> None:
    module = _load_entrypoint()

    assert module.main(["run", "--dry-run", "--json", "--lookback", "2"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "run"
    assert len(payload["weeks"]) == 2
    assert all(date.fromisoformat(week).isoweekday() == 1 for week in payload["weeks"])


def test_weekly_flow_runs_one_isolated_subflow_per_week(monkeypatch) -> None:
    from pipelines.weekly_performance import flow as flow_module

    weeks = [date(2026, 7, 6), date(2026, 7, 13)]
    subflow = _FakeSubflow(
        [_FakeState(value="semana-1"), _FakeState(value="semana-2")]
    )
    monkeypatch.setattr(
        flow_module, "resolve_target_weeks", lambda lookback_weeks: weeks
    )
    monkeypatch.setattr(flow_module, "process_week", subflow)

    assert flow_module.weekly_flow.fn(lookback_weeks=2) == ["semana-1", "semana-2"]

    assert [call[0] for call in subflow.calls] == weeks
    for _, kwargs in subflow.calls:
        assert kwargs == {"triggered_by": "schedule", "force": False, "reason": None}


def test_weekly_flow_reports_failed_weeks_without_hiding_them(monkeypatch) -> None:
    from pipelines.weekly_performance import flow as flow_module

    subflow = _FakeSubflow([_FakeState(value="ok"), _FakeState(ok=False)])
    monkeypatch.setattr(
        flow_module,
        "resolve_target_weeks",
        lambda lookback_weeks: [date(2026, 7, 6), date(2026, 7, 13)],
    )
    monkeypatch.setattr(flow_module, "process_week", subflow)

    with pytest.raises(RuntimeError, match="1 de 2 semanas fallaron"):
        flow_module.weekly_flow.fn(lookback_weeks=2)

    # El padre siguió ejecutando el resto de semanas tras la falla.
    assert len(subflow.calls) == 2


def test_backfill_through_entrypoint_is_idempotent(
    sqlite_engine: Engine, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL_PIPELINE", str(sqlite_engine.url))
    clear_engine_cache()

    module = _load_entrypoint()
    week_start = WEEKS[1]

    for _ in range(2):
        exit_code = module.main(
            ["backfill", "--week", week_start.isoformat(), "--json"]
        )
        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["week_start"] == week_start.isoformat()
        assert payload[0]["status"] in {"success", "skipped"}

    performance = get_reporting_tables(None).performance
    with sqlite_engine.connect() as conn:
        rows = (
            conn.execute(
                select(performance).where(performance.c.week_start == week_start)
            )
            .mappings()
            .all()
        )

    assert len(rows) == 2
    by_key = {(row["warehouse"], row["client_id"]): row for row in rows}
    assert set(by_key) == set(EXPECTED)
    for key, expected in EXPECTED.items():
        for field, value in expected.items():
            assert float(by_key[key][field]) == pytest.approx(value, abs=1e-6)
