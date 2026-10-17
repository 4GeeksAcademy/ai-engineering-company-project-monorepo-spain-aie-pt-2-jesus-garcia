import logging
from uuid import uuid4

import pytest

EVENT_TEMPLATE = {
    "event_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    "timestamp": "2026-10-05T20:34:00.000Z",
    "session_id": "session-abc",
    "user_id": "1",
    "event_type": "inbound_order_created",
    "schema_version": "1.0.0",
    "request_id": "req-1",
    "source": "backend",
    "app": "backoffice",
    "properties": {
        "warehouse": "los_angeles",
        "client_id": "fashion-co",
        "product_id": "CLT-SNK-W-42",
        "product_category": "fashion",
        "quantity": 20,
    },
}


def make_event(**overrides):
    event = {**EVENT_TEMPLATE, "event_id": str(uuid4())}
    event.update(overrides)
    return event


def test_ingest_valid_batch_returns_received_count(client):
    payload = {"events": [make_event(), make_event(event_type="outbound_order_created")]}
    response = client.post("/telemetry/events", json=payload)
    assert response.status_code == 200
    assert response.json() == {"received": 2}


def test_ingest_empty_batch_returns_zero(client):
    response = client.post("/telemetry/events", json={"events": []})
    assert response.status_code == 200
    assert response.json() == {"received": 0}


def test_ingest_missing_events_field_defaults_to_zero(client):
    response = client.post("/telemetry/events", json={})
    assert response.status_code == 200
    assert response.json() == {"received": 0}


def test_ingest_logs_count_and_event_types(client, caplog):
    caplog.set_level(logging.INFO, logger="api.telemetry")
    payload = {
        "events": [
            make_event(event_type="login_succeeded", source="frontend"),
            make_event(event_type="login_succeeded", source="frontend"),
            make_event(event_type="page_view", source="frontend"),
        ]
    }
    response = client.post("/telemetry/events", json=payload)
    assert response.status_code == 200
    assert response.json() == {"received": 3}
    records = [r.getMessage() for r in caplog.records if r.name == "api.telemetry"]
    assert any("Telemetry events received: 3" in message for message in records)
    assert any("login_succeeded" in message and "page_view" in message for message in records)


def test_ingest_rejects_unknown_event_type(client):
    response = client.post("/telemetry/events", json={"events": [make_event(event_type="nope")]})
    assert response.status_code == 422


def test_ingest_rejects_missing_envelope_field(client):
    event = make_event()
    del event["session_id"]
    response = client.post("/telemetry/events", json={"events": [event]})
    assert response.status_code == 422


def test_ingest_rejects_invalid_event_id(client):
    response = client.post("/telemetry/events", json={"events": [make_event(event_id="not-a-uuid")]})
    assert response.status_code == 422


def test_ingest_rejects_invalid_schema_version(client):
    response = client.post("/telemetry/events", json={"events": [make_event(schema_version="v1")]})
    assert response.status_code == 422


def test_ingest_rejects_invalid_timestamp(client):
    response = client.post("/telemetry/events", json={"events": [make_event(timestamp="ayer")]})
    assert response.status_code == 422


@pytest.mark.parametrize("source,app", [("frontend", "backoffice"), ("backend", "website")])
def test_ingest_accepts_source_and_app_combinations(client, source, app):
    response = client.post(
        "/telemetry/events",
        json={"events": [make_event(source=source, app=app)]},
    )
    assert response.status_code == 200
    assert response.json() == {"received": 1}


def test_ingest_accepts_null_user_and_request_id(client):
    event = make_event(user_id=None, request_id=None)
    response = client.post("/telemetry/events", json={"events": [event]})
    assert response.status_code == 200
    assert response.json() == {"received": 1}


def test_ingest_rejects_unknown_source(client):
    response = client.post("/telemetry/events", json={"events": [make_event(source="cli")]})
    assert response.status_code == 422
