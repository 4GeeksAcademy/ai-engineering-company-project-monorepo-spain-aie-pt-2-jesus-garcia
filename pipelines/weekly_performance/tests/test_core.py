from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import delete, insert, select

from pipelines.weekly_performance.core import (
    aggregate_kpis,
    evaluate_quality,
    extract_week,
    load_week,
    normalize_validate,
    resolve_target_weeks,
    run_week,
)
from pipelines.weekly_performance.schema import telemetry_table
from pipelines.weekly_performance.sql import tables_for
from pipelines.weekly_performance.tests.factories import (
    EXPECTED,
    WEEKS,
    week_events,
)

W1 = WEEKS[0]
W2 = WEEKS[1]


def _performance_rows(engine):
    tables = tables_for(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.performance).order_by(
                tables.performance.c.warehouse,
                tables.performance.c.client_id,
            )
        ).mappings().all()
    return [dict(row) for row in rows]


def _normalized_snapshot(rows):
    snapshot = []
    for row in rows:
        item = dict(row)
        item.pop("computed_at", None)
        item["discrepancy_rate"] = float(item["discrepancy_rate"])
        snapshot.append(item)
    return snapshot


def test_resolve_target_weeks_on_monday():
    assert resolve_target_weeks(3, today=date(2026, 7, 27)) == [
        date(2026, 7, 20),
        date(2026, 7, 13),
        date(2026, 7, 6),
    ]


def test_resolve_target_weeks_midweek():
    assert resolve_target_weeks(2, today=date(2026, 7, 29)) == [
        date(2026, 7, 20),
        date(2026, 7, 13),
    ]


def test_resolve_target_weeks_across_year_boundary():
    # Jueves 1 de enero de 2026 -> última semana cerrada: lunes 22 de diciembre.
    assert resolve_target_weeks(2, today=date(2026, 1, 1)) == [
        date(2025, 12, 22),
        date(2025, 12, 15),
    ]


def test_resolve_target_weeks_rejects_invalid_lookback():
    with pytest.raises(ValueError):
        resolve_target_weeks(0)


def test_extract_week_only_reads_target_week(seeded):
    assert len(extract_week(seeded, W1)) == 10
    assert len(extract_week(seeded, W2)) == 12


def test_normalize_dedupes_and_quarantines(seeded):
    rows = extract_week(seeded, W2)
    result = normalize_validate(rows, W2)

    assert len(result.valid) == 10
    assert len(result.rejects) == 2
    assert result.duplicates == 0
    assert {reject["reason"] for reject in result.rejects} == {
        "invalid_warehouse",
        "missing_client_id",
    }

    with_duplicate = normalize_validate(rows + [rows[0]], W2)
    assert with_duplicate.duplicates == 1
    assert len(with_duplicate.valid) == 10


def test_normalize_rejects_discrepancy_without_order_id():
    row = {
        "event_id": "disc-no-order",
        "event_type": "inventory_discrepancy_detected",
        "timestamp": datetime.now(timezone.utc),
        "tags": {
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "quantity": 1,
        },
    }
    result = normalize_validate([row], W1)
    assert result.valid == []
    assert result.rejects[0]["reason"] == "missing_order_id"


def test_aggregate_known_totals(seeded):
    result = normalize_validate(extract_week(seeded, W1), W1)
    kpis = {(row["warehouse"], row["client_id"]): row for row in aggregate_kpis(result.valid)}

    assert kpis[("los_angeles", "fashion-co")] == {
        "warehouse": "los_angeles",
        "client_id": "fashion-co",
        **EXPECTED[("los_angeles", "fashion-co")],
    }
    assert kpis[("zaragoza", "home-deco")] == {
        "warehouse": "zaragoza",
        "client_id": "home-deco",
        **EXPECTED[("zaragoza", "home-deco")],
    }


def test_aggregate_deduplicates_outbound_orders():
    valid = [
        {
            "event_id": "e1",
            "event_type": "outbound_order_created",
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "quantity": 1,
            "order_key": "order-1",
        },
        {
            "event_id": "e2",
            "event_type": "outbound_order_created",
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "quantity": 1,
            "order_key": "order-1",
        },
    ]
    assert aggregate_kpis(valid)[0]["outbound_orders_count"] == 1


def test_quality_warns_on_small_sample_reject_rate():
    kpis = [{"warehouse": "los_angeles", "client_id": "fashion-co", **EXPECTED[("los_angeles", "fashion-co")]}]
    report = evaluate_quality(
        kpis, rejects=2, total_rows=12, week_start=W2
    )
    assert report.status == "warning"
    assert any("small_sample" in warning for warning in report.warnings)


def test_quality_blocks_high_reject_rate_in_large_sample():
    kpis = [{"warehouse": "los_angeles", "client_id": "fashion-co", **EXPECTED[("los_angeles", "fashion-co")]}]
    report = evaluate_quality(kpis, rejects=10, total_rows=100, week_start=W2)
    assert report.status == "failed"
    assert any("reject_rate" in blocker for blocker in report.blockers)


def test_quality_blocks_invalid_rate():
    kpis = [
        {
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "inbound_units_count": 1,
            "outbound_orders_count": 1,
            "stockout_events_count": 0,
            "discrepancy_events_count": 2,
            "discrepancy_rate": 2.0,
        }
    ]
    report = evaluate_quality(kpis, rejects=0, total_rows=4, week_start=W1)
    assert report.status == "failed"
    assert any("invalid_discrepancy_rate" in blocker for blocker in report.blockers)


def test_quality_blocks_missing_instrumentation_after_since():
    kpis = [
        {
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "inbound_units_count": 1,
            "outbound_orders_count": 1,
            "stockout_events_count": 0,
            "discrepancy_events_count": 0,
            "discrepancy_rate": 0.0,
        }
    ]
    report = evaluate_quality(
        kpis,
        rejects=0,
        total_rows=4,
        week_start=W1,
        instrumentation_since=date(2026, 1, 1),
    )
    assert report.status == "failed"
    assert "instrumentation_missing" in report.blockers


def test_run_week_end_to_end(seeded):
    result = run_week(seeded, W1, triggered_by="test")

    assert result.status == "success"
    assert result.rows_written == 2
    assert result.quality_status == "passed"
    assert len(_performance_rows(seeded)) == 2


def test_run_three_weeks_accumulates_results(seeded):
    results = [run_week(seeded, week, triggered_by="test") for week in WEEKS]

    assert [result.status for result in results] == ["success", "success", "success"]
    assert len(_performance_rows(seeded)) == 6


def test_week_with_quarantine_succeeds_with_warning(seeded):
    result = run_week(seeded, W2, triggered_by="test")

    assert result.status == "success"
    assert result.quality_status == "warning"
    assert result.rows_rejected == 2
    assert result.rows_valid == 10


def test_run_week_is_idempotent(seeded):
    first = run_week(seeded, W1, triggered_by="test")
    before = _normalized_snapshot(_performance_rows(seeded))

    second = run_week(seeded, W1, triggered_by="test", force=True)
    after = _normalized_snapshot(_performance_rows(seeded))

    assert first.status == second.status == "success"
    assert before == after


def test_run_week_skips_unchanged_fingerprint(seeded):
    run_week(seeded, W1, triggered_by="test")
    second = run_week(seeded, W1, triggered_by="test")

    assert second.status == "skipped"
    assert second.skipped_reason == "fingerprint_unchanged"


def test_reconcile_removes_obsolete_combination(seeded):
    run_week(seeded, W1, triggered_by="test")

    table = telemetry_table()
    ids = [
        event["event_id"]
        for event in week_events(W1)
        if event["tags"]["warehouse"] == "zaragoza"
    ]
    with seeded.begin() as conn:
        conn.execute(delete(table).where(table.c.event_id.in_(ids)))

    run_week(seeded, W1, triggered_by="test", force=True)
    rows = _performance_rows(seeded)
    assert [row["warehouse"] for row in rows] == ["los_angeles"]


def test_frozen_week_is_skipped(seeded):
    tables = tables_for(seeded)
    with seeded.begin() as conn:
        conn.execute(
            insert(tables.published).values(
                week_start=W1,
                published_at=datetime.now(timezone.utc),
                published_by="test",
                frozen=True,
            )
        )

    result = run_week(seeded, W1, triggered_by="test")
    assert result.status == "skipped"
    assert result.skipped_reason == "frozen"
    assert _performance_rows(seeded) == []


def test_load_rejects_non_monday(seeded):
    with pytest.raises(ValueError):
        load_week(seeded, [], date(2026, 7, 7))


def test_run_ledger_and_steps(seeded):
    result = run_week(seeded, W1, triggered_by="test")
    tables = tables_for(seeded)

    with seeded.connect() as conn:
        run = conn.execute(
            select(tables.runs).where(tables.runs.c.run_id == result.run_id)
        ).mappings().one()
        steps = conn.execute(
            select(tables.steps.c.step).where(tables.steps.c.run_id == result.run_id)
        ).scalars().all()

    assert run["status"] == "success"
    assert run["rows_written"] == 2
    assert set(steps) == {
        "extract",
        "normalize",
        "aggregate",
        "quality",
        "load",
        "reconcile",
    }
