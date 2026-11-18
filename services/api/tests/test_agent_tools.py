"""Tests de integración de las tools de lectura del agente.

Verifican que las tools leen de los servicios reales (TinyDB y SQLModel), que
son de solo lectura, que el timeout se respeta y que los fallbacks son
honestos. No usan datos simulados.
"""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError
from sqlalchemy import delete as sql_delete
from sqlalchemy import func
from sqlmodel import Session, delete, select

from app.agent.tools.contracts import (
    IncidentLookupInput,
    InventoryLookupInput,
)
from app.agent.tools import incidents as incidents_tool
from app.agent.tools import inventory as inventory_tool
from app.agent.tools.incidents import lookup_incident
from app.agent.tools.inventory import lookup_inventory
from database import engine, get_tinydb
from models import InventoryDiscrepancy, SKU, StockEntry, StockExit
from app.telemetry.outbox import outbox_table


@pytest.fixture(autouse=True)
def _clean_inventory(client):
    """Tablas SQL limpias y creadas (el lifespan de ``client`` hace create_all)."""
    with Session(engine) as session:
        session.exec(delete(InventoryDiscrepancy))
        session.exec(delete(StockExit))
        session.exec(delete(StockEntry))
        session.exec(delete(SKU))
        session.execute(sql_delete(outbox_table(engine)))
        session.commit()
    yield
    with Session(engine) as session:
        session.exec(delete(InventoryDiscrepancy))
        session.exec(delete(StockExit))
        session.exec(delete(StockEntry))
        session.exec(delete(SKU))
        session.execute(sql_delete(outbox_table(engine)))
        session.commit()


def _insert_incident(**overrides) -> int:
    db = get_tinydb()
    try:
        values = {
            "title": "Paquete extraviado",
            "description": "El paquete no aparece en tránsito.",
            "origin": "customer",
            "branch": "la_warehouse",
            "category": "lost_parcel",
            "status": "open",
            "created_at": "2026-11-01T10:00:00+00:00",
            "updated_at": "2026-11-01T10:00:00+00:00",
        }
        values.update(overrides)
        return db.table("incidents").insert(values)
    finally:
        db.close()


def _seed_inventory(sku_code: str = "CLT-SNK-W-42", inbound: int = 50, outbound: int = 3) -> int:
    with Session(engine) as session:
        sku = SKU(
            name="Classic White Sneaker - Size 42",
            sku_code=sku_code,
            warehouse="los_angeles",
        )
        session.add(sku)
        session.commit()
        session.refresh(sku)
        session.add(
            StockEntry(
                sku_id=sku.id,
                quantity=inbound,
                warehouse="los_angeles",
                user_uuid="test-user",
            )
        )
        session.add(
            StockExit(
                sku_id=sku.id,
                quantity=outbound,
                warehouse="los_angeles",
                user_uuid="test-user",
            )
        )
        session.commit()
        return sku.id


def _count_rows() -> tuple[int, int, int]:
    with Session(engine) as session:
        skus = session.exec(select(func.count()).select_from(SKU)).one()
        entries = session.exec(select(func.count()).select_from(StockEntry)).one()
        exits = session.exec(select(func.count()).select_from(StockExit)).one()
    return int(skus), int(entries), int(exits)


class TestIncidentLookup:
    def test_returns_the_real_record_by_id(self):
        incident_id = _insert_incident(status="in_progress")

        result = lookup_incident(IncidentLookupInput(ticket_id=incident_id))

        assert result.ok is True
        assert result.found is True
        assert len(result.incidents) == 1
        incident = result.incidents[0]
        assert incident.id == str(incident_id)
        assert incident.status == "in_progress"
        assert incident.category == "lost_parcel"
        assert incident.origin == "customer"
        assert incident.created_at == "2026-11-01T10:00:00+00:00"

    def test_filters_match_the_rest_api(self):
        _insert_incident(status="open")
        _insert_incident(status="resolved", title="Entrega fallida")

        result = lookup_incident(IncidentLookupInput(status="open"))

        assert result.ok is True
        assert result.found is True
        assert len(result.incidents) == 1
        assert result.incidents[0].status == "open"

    def test_is_read_only(self):
        incident_id = _insert_incident()
        db = get_tinydb()
        before = len(db.table("incidents").all())
        db.close()

        lookup_incident(IncidentLookupInput(ticket_id=incident_id))

        db = get_tinydb()
        after = len(db.table("incidents").all())
        db.close()
        assert after == before

    def test_not_found_is_honest(self):
        result = lookup_incident(IncidentLookupInput(ticket_id=999999))

        assert result.ok is False
        assert result.found is False
        assert result.error == "not_found"
        assert "999999" in result.message

    def test_invalid_input_returns_typed_error(self):
        result = lookup_incident({"status": "open", "ticket_id": 0})

        assert result.ok is False
        assert result.error == "invalid_input"
        assert result.message

    def test_missing_criterion_is_rejected(self):
        with pytest.raises(ValidationError):
            IncidentLookupInput()

        result = lookup_incident({})
        assert result.error == "invalid_input"

    def test_timeout_returns_typed_error(self, monkeypatch):
        def slow(payload):
            time.sleep(0.2)

        monkeypatch.setattr(incidents_tool, "_read_incidents", slow)

        result = lookup_incident(
            IncidentLookupInput(ticket_id=1),
            timeout_seconds=0.01,
        )

        assert result.ok is False
        assert result.error == "timeout"

    def test_unavailable_service_returns_typed_error(self, monkeypatch):
        def boom(payload):
            raise RuntimeError("TinyDB no disponible")

        monkeypatch.setattr(incidents_tool, "_read_incidents", boom)

        result = lookup_incident(IncidentLookupInput(ticket_id=1))

        assert result.ok is False
        assert result.error == "unavailable"


class TestInventoryLookup:
    def test_returns_real_stock_from_sql(self):
        _seed_inventory()

        result = lookup_inventory(
            InventoryLookupInput(sku_code="CLT-SNK-W-42")
        )

        assert result.ok is True
        assert result.found is True
        assert len(result.items) == 1
        item = result.items[0]
        assert item.sku_code == "CLT-SNK-W-42"
        assert item.current_stock == 47
        assert item.current_stock_by_warehouse["los_angeles"] == 47
        assert item.current_stock_by_warehouse["zaragoza"] == 0

    def test_name_query_is_supported(self):
        _seed_inventory()

        result = lookup_inventory(
            InventoryLookupInput(name_query="classic white")
        )

        assert result.ok is True
        assert result.items[0].sku_code == "CLT-SNK-W-42"

    def test_is_read_only(self):
        _seed_inventory()
        before = _count_rows()

        lookup_inventory(InventoryLookupInput(sku_code="CLT-SNK-W-42"))

        assert _count_rows() == before

    def test_not_found_is_honest(self):
        result = lookup_inventory(
            InventoryLookupInput(sku_code="NO-EXISTE-999")
        )

        assert result.ok is False
        assert result.found is False
        assert result.error == "not_found"

    def test_invalid_input_returns_typed_error(self):
        with pytest.raises(ValidationError):
            InventoryLookupInput()

        result = lookup_inventory({})
        assert result.error == "invalid_input"

    def test_timeout_returns_typed_error(self, monkeypatch):
        def slow(payload):
            time.sleep(0.2)

        monkeypatch.setattr(inventory_tool, "_read_inventory", slow)

        result = lookup_inventory(
            InventoryLookupInput(sku_code="CLT-SNK-W-42"),
            timeout_seconds=0.01,
        )

        assert result.ok is False
        assert result.error == "timeout"

    def test_missing_engine_returns_unavailable(self, monkeypatch):
        import database

        monkeypatch.setattr(database, "engine", None)

        result = lookup_inventory(
            InventoryLookupInput(sku_code="CLT-SNK-W-42")
        )

        assert result.ok is False
        assert result.error == "unavailable"
