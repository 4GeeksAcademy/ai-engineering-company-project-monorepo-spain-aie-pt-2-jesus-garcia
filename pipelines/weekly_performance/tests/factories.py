"""Datos deterministas para los tests del pipeline."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Engine, insert

from ..schema import telemetry_table
from ..settings import (
    DISCREPANCY,
    INBOUND,
    OUTBOUND,
    STOCKOUT,
)

WEEKS: tuple[date, ...] = (
    date(2026, 7, 6),
    date(2026, 7, 13),
    date(2026, 7, 20),
)

#: Totales esperados para (los_angeles, fashion-co) y (zaragoza, home-deco).
EXPECTED: dict[tuple[str, str], dict] = {
    ("los_angeles", "fashion-co"): {
        "inbound_units_count": 150,
        "outbound_orders_count": 3,
        "stockout_events_count": 1,
        "discrepancy_events_count": 1,
        "discrepancy_rate": 0.333333,
    },
    ("zaragoza", "home-deco"): {
        "inbound_units_count": 70,
        "outbound_orders_count": 2,
        "stockout_events_count": 0,
        "discrepancy_events_count": 0,
        "discrepancy_rate": 0.0,
    },
}


def _ts(week_start: date, day: int, hour: int = 10) -> datetime:
    return datetime.combine(
        week_start + timedelta(days=day),
        time(hour=hour),
        tzinfo=timezone.utc,
    )


def _event(
    event_id: str,
    event_type: str,
    timestamp: datetime,
    **tags,
) -> dict:
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "session_id": "seed",
        "user_id": "seed-user",
        "schema_version": "2.0.0",
        "request_id": None,
        "source": "backend",
        "service": "backoffice",
        "tags": tags,
        "received_at": timestamp,
    }


def week_events(week_start: date) -> list[dict]:
    """10 eventos válidos por semana: 7 de LA/fashion-co y 3 de ZG/home-deco."""

    suffix = week_start.isoformat()
    return [
        _event(
            f"in-la-{suffix}-1",
            INBOUND,
            _ts(week_start, 0, 9),
            warehouse="los_angeles",
            client_id="fashion-co",
            quantity=100,
            order_id=f"in-la-{suffix}-1",
        ),
        _event(
            f"in-la-{suffix}-2",
            INBOUND,
            _ts(week_start, 1, 9),
            warehouse="los_angeles",
            client_id="fashion-co",
            quantity=50,
            order_id=f"in-la-{suffix}-2",
        ),
        _event(
            f"out-la-{suffix}-1",
            OUTBOUND,
            _ts(week_start, 0, 10),
            warehouse="los_angeles",
            client_id="fashion-co",
            quantity=10,
            order_id=f"out-la-{suffix}-1",
        ),
        _event(
            f"out-la-{suffix}-2",
            OUTBOUND,
            _ts(week_start, 2, 10),
            warehouse="los_angeles",
            client_id="fashion-co",
            quantity=20,
            order_id=f"out-la-{suffix}-2",
        ),
        _event(
            f"out-la-{suffix}-3",
            OUTBOUND,
            _ts(week_start, 4, 10),
            warehouse="los_angeles",
            client_id="fashion-co",
            quantity=30,
            order_id=f"out-la-{suffix}-3",
        ),
        _event(
            f"stock-la-{suffix}-1",
            STOCKOUT,
            _ts(week_start, 3, 10),
            warehouse="los_angeles",
            client_id="fashion-co",
            quantity=5,
            min_stock=10,
        ),
        _event(
            f"disc-la-{suffix}-1",
            DISCREPANCY,
            _ts(week_start, 4, 11),
            warehouse="los_angeles",
            client_id="fashion-co",
            quantity=5,
            order_id=f"out-la-{suffix}-1",
            incident_id=f"inc-la-{suffix}-1",
        ),
        _event(
            f"in-zg-{suffix}-1",
            INBOUND,
            _ts(week_start, 0, 11),
            warehouse="zaragoza",
            client_id="home-deco",
            quantity=70,
            order_id=f"in-zg-{suffix}-1",
        ),
        _event(
            f"out-zg-{suffix}-1",
            OUTBOUND,
            _ts(week_start, 1, 11),
            warehouse="zaragoza",
            client_id="home-deco",
            quantity=15,
            order_id=f"out-zg-{suffix}-1",
        ),
        _event(
            f"out-zg-{suffix}-2",
            OUTBOUND,
            _ts(week_start, 3, 11),
            warehouse="zaragoza",
            client_id="home-deco",
            quantity=25,
            order_id=f"out-zg-{suffix}-2",
        ),
    ]


def invalid_events(week_start: date) -> list[dict]:
    """Dos eventos que deben ir a cuarentena (no contaminan los KPIs)."""

    suffix = week_start.isoformat()
    return [
        _event(
            f"bad-warehouse-{suffix}",
            INBOUND,
            _ts(week_start, 2, 9),
            warehouse="madrid",
            client_id="fashion-co",
            quantity=10,
        ),
        _event(
            f"missing-client-{suffix}",
            OUTBOUND,
            _ts(week_start, 2, 12),
            warehouse="zaragoza",
            quantity=10,
            order_id=f"out-missing-{suffix}",
        ),
    ]


def seed_three_weeks(engine: Engine) -> list[date]:
    """Inserta 3 semanas; la segunda incluye 2 eventos inválidos."""

    rows: list[dict] = []
    for week_start in WEEKS:
        rows.extend(week_events(week_start))
    rows.extend(invalid_events(WEEKS[1]))

    with engine.begin() as conn:
        conn.execute(insert(telemetry_table()), rows)
    return list(WEEKS)
