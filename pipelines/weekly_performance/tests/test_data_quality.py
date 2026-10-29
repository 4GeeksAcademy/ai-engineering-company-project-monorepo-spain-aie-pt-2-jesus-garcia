from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import insert

from pipelines.weekly_performance.core import (
    evaluate_quality,
    previous_week_kpis,
    reconcile_source,
    run_week,
)
from pipelines.weekly_performance.schema import stock_table
from pipelines.weekly_performance.tests.factories import WEEKS

W1 = WEEKS[0]
W2 = WEEKS[1]


def _kpi(warehouse: str = "los_angeles", client: str = "fashion-co", inbound: int = 100):
    return {
        "warehouse": warehouse,
        "client_id": client,
        "inbound_units_count": inbound,
        "outbound_orders_count": 2,
        "stockout_events_count": 0,
        "discrepancy_events_count": 0,
        "discrepancy_rate": 0.0,
    }


def test_quality_warns_on_volume_variation():
    report = evaluate_quality(
        [_kpi(inbound=200)],
        rejects=0,
        total_rows=10,
        week_start=W2,
        previous_kpis=[_kpi(inbound=100)],
    )
    assert report.status == "warning"
    assert any("volume_variation" in warning for warning in report.warnings)


def test_quality_warns_on_active_combination_drop():
    report = evaluate_quality(
        [_kpi()],
        rejects=0,
        total_rows=10,
        week_start=W2,
        previous_kpis=[_kpi(), _kpi(client="home-deco")],
    )
    assert report.status == "warning"
    assert any("active_combinations_drop" in warning for warning in report.warnings)


def test_quality_warns_on_stale_source():
    report = evaluate_quality(
        [_kpi()],
        rejects=0,
        total_rows=10,
        week_start=W2,
        source_freshness_hours=30,
    )
    assert report.status == "warning"
    assert any("stale_source" in warning for warning in report.warnings)


def test_previous_week_kpis_returns_persisted_rows(seeded):
    run_week(seeded, W1, triggered_by="test")
    previous = previous_week_kpis(seeded, W2)
    assert len(previous) == 2
    assert {row["warehouse"] for row in previous} == {"los_angeles", "zaragoza"}


def _insert_stock(engine, table_name: str, count: int, day: int = 0):
    table = stock_table(table_name)
    timestamp = datetime.combine(
        W1 + timedelta(days=day), time(hour=9), tzinfo=timezone.utc
    )
    with engine.begin() as conn:
        conn.execute(
            insert(table),
            [
                {
                    "sku_id": 1,
                    "quantity": 1,
                    "warehouse": "los_angeles",
                    "user_uuid": "test",
                    "created_at": timestamp,
                }
                for _ in range(count)
            ],
        )


def test_reconcile_source_matches_orders_and_events(seeded):
    # Día 0 de W1: 2 inbound y 1 outbound en telemetría.
    _insert_stock(seeded, "stock_entry", 2)
    _insert_stock(seeded, "stock_exit", 1)

    rows = reconcile_source(seeded, W1, W1)

    assert len(rows) == 1
    assert rows[0]["inbound_orders"] == 2
    assert rows[0]["inbound_events"] == 2
    assert rows[0]["outbound_orders"] == 1
    assert rows[0]["outbound_events"] == 1
    assert rows[0]["ok"] is True


def test_reconcile_source_detects_missing_events(seeded):
    _insert_stock(seeded, "stock_entry", 3)
    _insert_stock(seeded, "stock_exit", 1)

    rows = reconcile_source(seeded, W1, W1)

    assert rows[0]["delta_inbound"] == -1
    assert rows[0]["ok"] is False
