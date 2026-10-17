import logging

import pytest
from sqlmodel import Session, delete

from database import engine
from models import SKU, StockEntry, StockExit

EMIT_LOGGER = "api.telemetry.emit"


@pytest.fixture(autouse=True)
def _clean_inventory(client):
    with Session(engine) as session:
        session.exec(delete(StockExit))
        session.exec(delete(StockEntry))
        session.exec(delete(SKU))
        session.commit()
    yield
    with Session(engine) as session:
        session.exec(delete(StockExit))
        session.exec(delete(StockEntry))
        session.exec(delete(SKU))
        session.commit()


def _create_product(client, auth_headers, sku_code="CLT-T3L-1"):
    res = client.post(
        "/inventory/products",
        headers=auth_headers,
        json={"name": "Telemetry SKU", "sku_code": sku_code, "warehouse": "los_angeles"},
    )
    assert res.status_code == 201
    return res.json()


def _emitted_messages(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == EMIT_LOGGER]


def test_inbound_order_emits_mandatory_event(client, auth_headers, caplog):
    caplog.set_level(logging.INFO, logger=EMIT_LOGGER)
    sku = _create_product(client, auth_headers)

    res = client.post(
        "/inventory/orders/inbound",
        headers=auth_headers,
        json={"sku_id": sku["id"], "quantity": 20, "warehouse": "zaragoza"},
    )
    assert res.status_code == 201

    messages = _emitted_messages(caplog)
    assert any("inbound_order_created" in message for message in messages)
    assert any("CLT-T3L-1" in message for message in messages)


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
