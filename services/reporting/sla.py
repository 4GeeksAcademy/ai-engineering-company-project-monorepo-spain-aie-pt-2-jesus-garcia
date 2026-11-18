"""Alerta de umbral de negocio del reporting: SLA de entrega por país.

Regla definida por TrackFlow en el briefing de tiempo real: si el SLA de
entrega a tiempo cae **por debajo del 90 % en cualquiera de los dos países**
(Estados Unidos o España), se notifica de inmediato a Thomas Harry (CEO) y a
Ana Whitfield (Warehouse Operations). El pipeline semanal de desempeño no mide
entregas, así que este módulo lee el read model ``reporting.delivery_sla_weekly``
(el feed de última milla; el script ``scripts/seed_delivery_sla.py`` siembra
una semana demo reproducible).

La evaluación es determinista y sin LLM: compara el último dato publicado con
el umbral y publica ``sla_threshold_alert`` una sola vez por semana y país.
"""

from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlmodel import Session

from app.realtime.events import SLA_THRESHOLD_ALERT, publish_event

from .service import ReportNotFound

SLA_THRESHOLD_PCT = 90.0
SLA_COUNTRIES: tuple[str, ...] = ("US", "Spain")
WAREHOUSE_BY_COUNTRY: dict[str, str] = {
    "US": "los_angeles",
    "Spain": "zaragoza",
}

#: Destinatarios fijos de la regla de negocio (briefing §4).
SLA_RECIPIENTS: tuple[dict[str, str], ...] = (
    {"name": "Thomas Harry", "role": "CEO"},
    {"name": "Ana Whitfield", "role": "Warehouse Operations"},
)

TABLE_NAME = "delivery_sla_weekly"

Publisher = Callable[[str, dict[str, Any]], Any]

_alerted: set[str] = set()
_alerted_lock = threading.Lock()


def _schema_for(engine) -> str | None:  # type: ignore[no-untyped-def]
    return "reporting" if engine.dialect.name == "postgresql" else None


def _table_for(engine) -> Table:  # type: ignore[no-untyped-def]
    metadata = MetaData()
    return Table(
        TABLE_NAME,
        metadata,
        Column("id", String(36), primary_key=True),
        Column("week_start", Date, nullable=False),
        Column("country", String(20), nullable=False),
        Column("warehouse", String(64), nullable=False),
        Column("total_shipments", Integer, nullable=False),
        Column("on_time_shipments", Integer, nullable=False),
        Column("computed_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint(
            "week_start", "country", name="uq_delivery_sla_week_country"
        ),
        schema=_schema_for(engine),
    )


def ensure_sla_table(engine) -> None:  # type: ignore[no-untyped-def]
    """Crea el read model de forma idempotente (PostgreSQL y SQLite)."""

    if engine is None:
        return
    if engine.dialect.name == "postgresql":
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("create schema if not exists reporting")
                )
        except Exception:  # pragma: no cover - permisos del pooler
            pass
    _table_for(engine).metadata.create_all(engine)


def _qualified(session: Session) -> str:
    bind = session.get_bind()
    prefix = "reporting." if bind is not None and bind.dialect.name == "postgresql" else ""
    return f"{prefix}{TABLE_NAME}"


def _as_date(value) -> date | None:  # type: ignore[no-untyped-def]
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_datetime(value) -> datetime | None:  # type: ignore[no-untyped-def]
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _recipients() -> list[dict[str, str]]:
    return [dict(item) for item in SLA_RECIPIENTS]


def get_delivery_sla_status(
    session: Session,
    week_start: date | None = None,
):
    """Estado del SLA de la última semana publicada (o la indicada)."""

    from .schemas import DeliverySlaCountry, DeliverySlaStatus

    table = _qualified(session)
    if week_start is None:
        raw_week = session.execute(
            text(f"select max(week_start) from {table}")
        ).scalar()
        if raw_week is None:
            raise ReportNotFound("No hay semanas de SLA calculadas.")
        week_start = _as_date(raw_week)

    rows = session.execute(
        text(
            f"""
            select country, warehouse, total_shipments, on_time_shipments,
                   computed_at
            from {table}
            where week_start = :week
            order by country
            """
        ),
        {"week": week_start},
    ).mappings().all()
    if not rows:
        raise ReportNotFound(f"No hay datos de SLA para la semana {week_start}.")

    countries: list[DeliverySlaCountry] = []
    for row in rows:
        total = int(row["total_shipments"])
        on_time = int(row["on_time_shipments"])
        on_time_pct = round(on_time / total * 100, 1) if total else None
        breached = on_time_pct is not None and on_time_pct < SLA_THRESHOLD_PCT
        countries.append(
            DeliverySlaCountry(
                country=row["country"],
                warehouse=row["warehouse"]
                or WAREHOUSE_BY_COUNTRY.get(row["country"]),
                on_time_pct=on_time_pct,
                total_shipments=total,
                on_time_shipments=on_time,
                breached=breached,
                recipients=_recipients() if breached else [],
            )
        )

    computed_at = max(
        (_as_datetime(row["computed_at"]) for row in rows), default=None
    )
    return DeliverySlaStatus(
        week_start=week_start,
        threshold_pct=SLA_THRESHOLD_PCT,
        breached=any(item.breached for item in countries),
        countries=countries,
        computed_at=computed_at,
    )


def build_sla_alert_payload(
    status, country, detected_at: datetime | None = None
) -> dict[str, Any]:
    """Payload del evento ``sla_threshold_alert`` (campos de la regla)."""

    moment = detected_at or datetime.now(timezone.utc)
    return {
        "alert_id": f"sla:{status.week_start.isoformat()}:{country.country}",
        "metric": "on_time_delivery_pct",
        "country": country.country,
        "warehouse": country.warehouse,
        "week_start": status.week_start.isoformat(),
        "threshold_pct": SLA_THRESHOLD_PCT,
        "on_time_pct": country.on_time_pct,
        "total_shipments": country.total_shipments,
        "on_time_shipments": country.on_time_shipments,
        "breached": True,
        "recipients": [
            item.model_dump() if hasattr(item, "model_dump") else dict(item)
            for item in country.recipients
        ],
        "detected_at": _iso(moment),
    }


def _claim_alert(alert_id: str) -> bool:
    """Idempotencia por proceso: una alerta por (semana, país)."""

    with _alerted_lock:
        if alert_id in _alerted:
            return False
        _alerted.add(alert_id)
        return True


def reset_sla_alerts() -> None:
    with _alerted_lock:
        _alerted.clear()


def evaluate_sla_alerts(
    session: Session,
    *,
    week_start: date | None = None,
    publisher: Publisher | None = None,
) -> tuple[Any, list[dict[str, Any]]]:
    """Evalúa el umbral y publica una alerta por país en breach.

    Devuelve el estado completo y los payloads publicados (vacío si no hay
    breach o si la alerta ya se emitió para esa semana y país).
    """

    publish = publisher or publish_event
    status = get_delivery_sla_status(session, week_start)
    published: list[dict[str, Any]] = []
    for country in status.countries:
        if not country.breached:
            continue
        payload = build_sla_alert_payload(status, country)
        if not _claim_alert(payload["alert_id"]):
            continue
        publish(SLA_THRESHOLD_ALERT, payload)
        published.append(payload)
    return status, published
