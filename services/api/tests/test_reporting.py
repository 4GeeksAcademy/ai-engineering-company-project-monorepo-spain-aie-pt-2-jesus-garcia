from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from sqlalchemy import insert

# Permite importar el paquete de pipeline para crear el esquema `reporting` en
# el SQLite de tests. El API en producción no importa Prefect ni el pipeline.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import engine  # noqa: E402
from pipelines.weekly_performance.sql import (  # noqa: E402
    create_reporting_schema,
    tables_for,
)

W1 = date(2026, 7, 6)
W2 = date(2026, 7, 13)


@pytest.fixture(autouse=True)
def _reporting_schema():
    create_reporting_schema(engine)
    tables = tables_for(engine)
    with engine.begin() as conn:
        for table in (
            tables.revisions,
            tables.rejects,
            tables.steps,
            tables.runs,
            tables.watermarks,
            tables.published,
            tables.performance,
        ):
            conn.execute(table.delete())
    yield


def _performance(
    week_start: date,
    warehouse: str = "los_angeles",
    client_id: str = "fashion-co",
    inbound: int = 150,
    outbound: int = 3,
    stockout: int = 1,
    discrepancy: int = 1,
    rate: float = 0.333333,
):
    tables = tables_for(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.performance).values(
                id=str(uuid4()),
                warehouse=warehouse,
                client_id=client_id,
                week_start=week_start,
                inbound_units_count=inbound,
                outbound_orders_count=outbound,
                stockout_events_count=stockout,
                discrepancy_events_count=discrepancy,
                discrepancy_rate=rate,
                computed_at=datetime.now(timezone.utc),
            )
        )


def _run(
    status: str = "success",
    week_start: date = W2,
    started_at: datetime | None = None,
):
    tables = tables_for(engine)
    run_id = str(uuid4())
    with engine.begin() as conn:
        conn.execute(
            insert(tables.runs).values(
                run_id=run_id,
                pipeline_name="weekly_warehouse_client_performance",
                week_start=week_start,
                status=status,
                triggered_by="test",
                started_at=started_at or datetime.now(timezone.utc),
                heartbeat_at=started_at or datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                rows_extracted=10,
                rows_valid=10,
                rows_rejected=0,
                rows_written=2,
                quality_status="passed",
                instrumentation_since=date(2026, 7, 1),
            )
        )
    return run_id


def _freeze(week_start: date = W2):
    tables = tables_for(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.published).values(
                week_start=week_start,
                published_at=datetime.now(timezone.utc),
                published_by="test",
                frozen=True,
            )
        )


def test_weekly_requires_auth(client):
    assert client.get("/reporting/weekly-warehouse-client-performance").status_code == 401


def test_weekly_returns_latest_week(client, auth_headers):
    _performance(W1)
    _performance(W2, warehouse="zaragoza", client_id="home-deco", inbound=70, outbound=2, stockout=0, discrepancy=0, rate=0.0)

    response = client.get(
        "/reporting/weekly-warehouse-client-performance", headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["week_start"] == W2.isoformat()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["warehouse"] == "zaragoza"
    assert body["entries"][0]["inbound_units_count"] == 70


def test_weekly_filters_requested_week(client, auth_headers):
    _performance(W1)
    _performance(W2)

    response = client.get(
        "/reporting/weekly-warehouse-client-performance",
        params={"week_start": W1.isoformat()},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["week_start"] == W1.isoformat()


def test_weekly_returns_frozen_and_stale(client, auth_headers):
    _performance(W2)
    _freeze(W2)
    _run(status="failed", week_start=W2)

    body = client.get(
        "/reporting/weekly-warehouse-client-performance", headers=auth_headers
    ).json()

    assert body["frozen"] is True
    assert body["stale"] is True


def test_weekly_404_without_data(client, auth_headers):
    response = client.get(
        "/reporting/weekly-warehouse-client-performance", headers=auth_headers
    )
    assert response.status_code == 404


def test_weekly_forbidden_for_user_role(client, user_headers):
    assert (
        client.get(
            "/reporting/weekly-warehouse-client-performance", headers=user_headers
        ).status_code
        == 403
    )


def test_latest_run(client, auth_headers):
    _run(status="success", week_start=W1)

    response = client.get("/reporting/pipeline-runs/latest", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["week_start"] == W1.isoformat()
    assert body["instrumentation_since"] == "2026-07-01"
    assert body["stale"] is False


def test_latest_run_404(client, auth_headers):
    assert (
        client.get("/reporting/pipeline-runs/latest", headers=auth_headers).status_code
        == 404
    )


def test_trigger_returns_409_when_running(client, auth_headers):
    _run(status="running", week_start=W1)

    response = client.post(
        "/reporting/pipeline-runs",
        json={"week_start": W1.isoformat()},
        headers=auth_headers,
    )

    assert response.status_code == 409


def test_trigger_returns_503_when_prefect_unavailable(
    client, auth_headers, monkeypatch
):
    from services.reporting import prefect_client

    def _raise(*_args, **_kwargs):
        raise prefect_client.PrefectUnavailable("down")

    monkeypatch.setattr(prefect_client, "trigger_weekly_flow", _raise)

    response = client.post("/reporting/pipeline-runs", headers=auth_headers)

    assert response.status_code == 503


def test_trigger_returns_202(client, auth_headers, monkeypatch):
    from services.reporting import prefect_client

    monkeypatch.setattr(
        prefect_client,
        "trigger_weekly_flow",
        lambda *_args, **_kwargs: {
            "run_id": "flow-run-1",
            "flow_run_id": "flow-run-1",
            "status": "scheduled",
        },
    )

    response = client.post(
        "/reporting/pipeline-runs",
        json={"week_start": W1.isoformat(), "lookback_weeks": 1},
        headers=auth_headers,
    )

    assert response.status_code == 202
    assert response.json()["run_id"] == "flow-run-1"


def test_weekly_response_is_cached(client, auth_headers, monkeypatch):
    from services.reporting import service

    _performance(W2)
    calls = {"count": 0}
    original = service.get_weekly_performance

    def _spy(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "get_weekly_performance", _spy)

    first = client.get(
        "/reporting/weekly-warehouse-client-performance", headers=auth_headers
    )
    second = client.get(
        "/reporting/weekly-warehouse-client-performance", headers=auth_headers
    )

    assert first.status_code == second.status_code == 200
    assert calls["count"] == 1
