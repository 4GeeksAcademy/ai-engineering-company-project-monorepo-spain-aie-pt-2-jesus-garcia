from __future__ import annotations

from prefect.testing.utilities import prefect_test_harness

from pipelines.weekly_performance.db import clear_engine_cache
from pipelines.weekly_performance.flow import process_week
from pipelines.weekly_performance.tests.factories import WEEKS


def test_process_week_flow_runs_with_tasks(seeded, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", str(seeded.url))
    clear_engine_cache()

    # El harness arranca/para el servidor dentro del contexto de pytest, antes
    # de que se cierren los streams de captura.
    with prefect_test_harness():
        result = process_week.fn(WEEKS[0])

    assert result.status == "success"
    assert result.rows_written == 2
