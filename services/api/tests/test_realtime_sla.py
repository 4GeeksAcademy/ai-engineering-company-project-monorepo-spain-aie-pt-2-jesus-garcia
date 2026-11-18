"""Tests de la alerta de umbral de negocio (SLA de entrega por país).

Regla del briefing: por debajo del 90 % en cualquiera de los dos países se
notifica a Thomas (CEO) y Ana (Warehouse Operations) con el evento nombrado
``sla_threshold_alert``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from database import engine as app_engine
from services.reporting import sla
from services.reporting.service import ReportNotFound

WEEK = date(2026, 11, 9)


@pytest.fixture(autouse=True)
def _reset_sla_alerts():
    sla.reset_sla_alerts()
    yield
    sla.reset_sla_alerts()


@pytest.fixture()
def sla_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sla.ensure_sla_table(engine)
    yield engine
    engine.dispose()


def _insert(engine, *, week: date, country: str, total: int, on_time: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into delivery_sla_weekly
                    (id, week_start, country, warehouse, total_shipments,
                     on_time_shipments, computed_at)
                values
                    (:id, :week, :country, :warehouse, :total, :on_time,
                     :computed_at)
                """
            ),
            {
                "id": str(uuid4()),
                "week": week,
                "country": country,
                "warehouse": sla.WAREHOUSE_BY_COUNTRY[country],
                "total": total,
                "on_time": on_time,
                "computed_at": datetime.now(timezone.utc),
            },
        )


def test_country_below_threshold_emits_sla_alert_with_recipients(sla_engine):
    _insert(sla_engine, week=WEEK, country="US", total=1520, on_time=1344)
    _insert(sla_engine, week=WEEK, country="Spain", total=980, on_time=912)

    published: list[tuple[str, dict]] = []
    with Session(sla_engine) as session:
        status, payloads = sla.evaluate_sla_alerts(
            session, publisher=lambda name, data: published.append((name, data))
        )

    assert status.breached is True
    assert status.threshold_pct == 90.0
    by_country = {item.country: item for item in status.countries}
    assert by_country["US"].breached is True
    assert by_country["US"].on_time_pct == 88.4
    assert by_country["Spain"].breached is False
    assert by_country["Spain"].on_time_pct == 93.1

    assert len(published) == 1
    name, data = published[0]
    assert name == "sla_threshold_alert"
    assert data["alert_id"] == "sla:2026-11-09:US"
    assert data["metric"] == "on_time_delivery_pct"
    assert data["country"] == "US"
    assert data["warehouse"] == "los_angeles"
    assert data["threshold_pct"] == 90.0
    assert data["on_time_pct"] == 88.4
    assert data["breached"] is True
    assert {item["name"] for item in data["recipients"]} == {
        "Thomas Harry",
        "Ana Whitfield",
    }
    assert {item["role"] for item in data["recipients"]} == {
        "CEO",
        "Warehouse Operations",
    }
    assert payloads == [data]


def test_country_above_threshold_does_not_emit(sla_engine):
    _insert(sla_engine, week=WEEK, country="US", total=1520, on_time=1444)
    _insert(sla_engine, week=WEEK, country="Spain", total=980, on_time=912)

    published: list[tuple[str, dict]] = []
    with Session(sla_engine) as session:
        status, payloads = sla.evaluate_sla_alerts(
            session, publisher=lambda name, data: published.append((name, data))
        )

    assert status.breached is False
    assert payloads == []
    assert published == []


def test_alert_is_idempotent_per_week_and_country(sla_engine):
    _insert(sla_engine, week=WEEK, country="US", total=1520, on_time=1344)

    published: list[tuple[str, dict]] = []
    recorder = lambda name, data: published.append((name, data))  # noqa: E731
    with Session(sla_engine) as session:
        _, first = sla.evaluate_sla_alerts(session, publisher=recorder)
        _, second = sla.evaluate_sla_alerts(session, publisher=recorder)

    assert len(first) == 1
    assert second == []
    assert len(published) == 1


def test_missing_sla_data_raises_report_not_found(sla_engine):
    with Session(sla_engine) as session:
        with pytest.raises(ReportNotFound):
            sla.get_delivery_sla_status(session)


def test_sla_endpoints_require_manager_and_report_the_breach(
    client, auth_headers, user_headers
):
    sla.ensure_sla_table(app_engine)
    with app_engine.begin() as connection:
        connection.execute(text("delete from delivery_sla_weekly"))
    _insert(app_engine, week=WEEK, country="US", total=1520, on_time=1344)
    _insert(app_engine, week=WEEK, country="Spain", total=980, on_time=912)

    try:
        assert client.get("/reporting/sla-status").status_code in (401, 403)
        assert (
            client.get("/reporting/sla-status", headers=user_headers).status_code
            == 403
        )

        status_response = client.get(
            "/reporting/sla-status", headers=auth_headers
        )
        assert status_response.status_code == 200, status_response.text
        body = status_response.json()
        assert body["threshold_pct"] == 90.0
        assert body["breached"] is True
        assert any(item["country"] == "US" for item in body["countries"])

        evaluate = client.post("/reporting/sla/evaluate", headers=auth_headers)
        assert evaluate.status_code == 200, evaluate.text
        payload = evaluate.json()
        assert payload["published"][0]["alert_id"] == "sla:2026-11-09:US"
        assert payload["published"][0]["threshold_pct"] == 90.0
    finally:
        with app_engine.begin() as connection:
            connection.execute(text("delete from delivery_sla_weekly"))
