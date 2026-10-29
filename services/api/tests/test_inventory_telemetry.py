import logging

import pytest
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlmodel import Session, delete

from app.telemetry.outbox import outbox_table
from database import engine
from models import InventoryDiscrepancy, SKU, StockEntry, StockExit

EMIT_LOGGER = "api.telemetry.emit"


@pytest.fixture(autouse=True)
def _clean_inventory(client):
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


def _create_product(
    client,
    auth_headers,
    sku_code="CLT-T3L-1",
    *,
    client_id: str | None = None,
    min_stock: int | None = None,
):
    res = client.post(
        "/inventory/products",
        headers=auth_headers,
        json={
            "name": "Telemetry SKU",
            "sku_code": sku_code,
            "warehouse": "los_angeles",
            "client_id": client_id,
            "min_stock": min_stock,
        },
    )
    assert res.status_code == 201
    return res.json()


def _emitted_messages(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == EMIT_LOGGER]


def _outbox_payloads() -> list[dict]:
    table = outbox_table(engine)
    with Session(engine) as session:
        return list(session.execute(select(table.c.payload)).scalars().all())


def test_inbound_order_emits_mandatory_event(client, auth_headers, caplog):
    caplog.set_level(logging.INFO, logger=EMIT_LOGGER)
    sku = _create_product(client, auth_headers, client_id="fashion-co")

    res = client.post(
        "/inventory/orders/inbound",
        headers=auth_headers,
        json={"sku_id": sku["id"], "quantity": 20, "warehouse": "zaragoza"},
    )
    assert res.status_code == 201

    messages = _emitted_messages(caplog)
    assert any("inbound_order_created" in message for message in messages)
    assert any("CLT-T3L-1" in message for message in messages)

    payloads = _outbox_payloads()
    assert len(payloads) == 1
    assert payloads[0]["event_type"] == "inbound_order_created"
    assert payloads[0]["properties"]["client_id"] == "fashion-co"
    assert payloads[0]["properties"]["quantity"] == 20


def test_outbound_order_emits_mandatory_event(client, auth_headers, caplog):
    caplog.set_level(logging.INFO, logger=EMIT_LOGGER)
    sku = _create_product(client, auth_headers)
    client.post(
        "/inventory/orders/inbound",
        headers=auth_headers,
        json={"sku_id": sku["id"], "quantity": 10, "warehouse": "los_angeles"},
    )
    caplog.clear()

    res = client.post(
        "/inventory/orders/outbound",
        headers=auth_headers,
        json={"sku_id": sku["id"], "quantity": 3, "warehouse": "los_angeles"},
    )
    assert res.status_code == 201

    messages = _emitted_messages(caplog)
    assert any("outbound_order_created" in message for message in messages)
    assert any(
        payload["event_type"] == "outbound_order_created"
        for payload in _outbox_payloads()
    )


def test_outbound_rejection_emits_event_without_writing(client, auth_headers, caplog):
    caplog.set_level(logging.INFO, logger=EMIT_LOGGER)
    sku = _create_product(client, auth_headers)

    res = client.post(
        "/inventory/orders/outbound",
        headers=auth_headers,
        json={"sku_id": sku["id"], "quantity": 5, "warehouse": "los_angeles"},
    )
    assert res.status_code == 400

    messages = _emitted_messages(caplog)
    assert any("outbound_rejected_insufficient_stock" in message for message in messages)


def test_outbound_crossing_min_stock_emits_stockout(client, auth_headers):
    sku = _create_product(
        client, auth_headers, client_id="fashion-co", min_stock=5
    )
    client.post(
        "/inventory/orders/inbound",
        headers=auth_headers,
        json={"sku_id": sku["id"], "quantity": 10, "warehouse": "los_angeles"},
    )
    client.post(
        "/inventory/orders/outbound",
        headers=auth_headers,
        json={"sku_id": sku["id"], "quantity": 6, "warehouse": "los_angeles"},
    )

    payloads = _outbox_payloads()
    stockouts = [
        payload for payload in payloads
        if payload["event_type"] == "stock_threshold_triggered"
    ]
    assert len(stockouts) == 1
    assert stockouts[0]["properties"]["min_stock"] == 5
    assert stockouts[0]["properties"]["deficit"] == 1


def test_discrepancy_emits_one_event_per_order(client, auth_headers):
    sku = _create_product(
        client, auth_headers, sku_code="DISC-1", client_id="fashion-co"
    )
    other = _create_product(
        client, auth_headers, sku_code="DISC-2", client_id="fashion-co"
    )

    first = client.post(
        "/inventory/discrepancies",
        headers=auth_headers,
        json={
            "order_id": "order-1",
            "sku_id": sku["id"],
            "warehouse": "los_angeles",
            "system_quantity": 10,
            "physical_quantity": 8,
        },
    )
    second = client.post(
        "/inventory/discrepancies",
        headers=auth_headers,
        json={
            "order_id": "order-1",
            "sku_id": other["id"],
            "warehouse": "los_angeles",
            "system_quantity": 5,
            "physical_quantity": 4,
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    events = [
        payload for payload in _outbox_payloads()
        if payload["event_type"] == "inventory_discrepancy_detected"
    ]
    assert len(events) == 1
    assert events[0]["properties"]["order_id"] == "order-1"
    assert events[0]["properties"]["client_id"] == "fashion-co"


def test_discrepancy_without_client_id_is_still_recorded(client, auth_headers):
    sku = _create_product(client, auth_headers, sku_code="DISC-NOCLIENT")

    res = client.post(
        "/inventory/discrepancies",
        headers=auth_headers,
        json={
            "order_id": "order-2",
            "sku_id": sku["id"],
            "warehouse": "los_angeles",
            "system_quantity": 3,
            "physical_quantity": 2,
        },
    )

    assert res.status_code == 201
    assert res.json()["client_id"] is None
    event = next(
        payload for payload in _outbox_payloads()
        if payload["event_type"] == "inventory_discrepancy_detected"
    )
    assert "client_id" not in event["properties"]


def test_product_exposes_client_and_min_stock(client, auth_headers):
    sku = _create_product(
        client, auth_headers, sku_code="CFG-1", client_id="home-deco", min_stock=7
    )
    assert sku["client_id"] == "home-deco"
    assert sku["min_stock"] == 7
