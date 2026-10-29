"""Fixtures de test: SQLite efímero, sin Supabase ni Docker."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys

# Permite ``from pipelines.weekly_performance...`` al ejecutar pytest desde
# cualquier directorio.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Evita que Prefect intente enviar logs a su API durante los tests y que el
# servidor efímero escriba en un stream ya cerrado al terminar pytest.
os.environ["PREFECT_LOGGING_TO_API_ENABLED"] = "false"
os.environ["PREFECT_LOGGING_TO_API_WHEN_MISSING_FLOW"] = "ignore"
os.environ.setdefault("PREFECT_LOGGING_SERVER_LEVEL", "CRITICAL")
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")
logging.getLogger("prefect").setLevel(logging.CRITICAL)

import pytest
from sqlalchemy import create_engine

from pipelines.weekly_performance.db import clear_engine_cache
from pipelines.weekly_performance.sql import (
    create_inventory_tables,
    create_reporting_schema,
    create_telemetry_table,
)
from pipelines.weekly_performance.tests.factories import seed_three_weeks


@pytest.fixture()
def engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'pipeline.db'}"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    create_reporting_schema(eng)
    create_telemetry_table(eng)
    create_inventory_tables(eng)
    yield eng
    eng.dispose()
    clear_engine_cache()


@pytest.fixture()
def seeded(engine):
    seed_three_weeks(engine)
    return engine
