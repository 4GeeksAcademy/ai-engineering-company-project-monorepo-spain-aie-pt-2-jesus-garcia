from __future__ import annotations

import pytest

from pipelines.weekly_performance.cli import main
from pipelines.weekly_performance.db import clear_engine_cache
from pipelines.weekly_performance.tests.factories import WEEKS


def test_cli_dry_run_does_not_touch_db(capsys):
    assert main(["run", "--dry-run", "--json", "--lookback", "2"]) == 0
    output = capsys.readouterr().out
    assert "weeks" in output
    assert "2026" in output


def test_cli_backfill_runs_week(seeded, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", str(seeded.url))
    clear_engine_cache()

    exit_code = main(
        [
            "backfill",
            "--week",
            WEEKS[0].isoformat(),
            "--json",
        ]
    )

    assert exit_code == 0
    assert '"status": "success"' in capsys.readouterr().out


def test_cli_force_requires_reason():
    with pytest.raises(SystemExit):
        main(["backfill", "--week", "2026-07-06", "--force"])
