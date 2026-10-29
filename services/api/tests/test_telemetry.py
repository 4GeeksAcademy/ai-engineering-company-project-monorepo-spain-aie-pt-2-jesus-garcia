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


def assert_counts(response, received: int, stored: int, rejected: int) -> None:
    assert response.status_code == 200
    assert response.json() == {
        "received": received,
        "stored": stored,
        "rejected": rejected,
    }


def test_ingest_valid_batch_returns_received_stored_and_rejected(client):
    payload = {"events": [make_event(), make_event(event_type="outbound_order_created")]}
    response = client.post("/telemetry/events", json=payload)
    assert_counts(response, received=2, stored=2, rejected=0)


def test_ingest_empty_batch_returns_zero(client):
    response = client.post("/telemetry/events", json={"events": []})
    assert_counts(response, received=0, stored=0, rejected=0)


def test_ingest_missing_events_field_defaults_to_zero(client):
    response = client.post("/telemetry/events", json={})
    assert_counts(response, received=0, stored=0, rejected=0)


def test_ingest_logs_received_accepted_and_stored(client, caplog):
    caplog.set_level(logging.INFO, logger="api.telemetry")
    payload = {
        "events": [
            make_event(event_type="login_succeeded", source="frontend"),
            make_event(event_type="login_succeeded", source="frontend"),
            make_event(event_type="page_view", source="frontend", properties={"path": "/", "app": "backoffice"}),
        ]
    }
    response = client.post(
        "/telemetry/events",
        json=payload,
        headers={"X-Telemetry-Consent": "granted"},
    )
    assert_counts(response, received=3, stored=3, rejected=0)
    records = [r.getMessage() for r in caplog.records if r.name == "api.telemetry"]
    assert any("Telemetry events received: 3" in message for message in records)
    assert any("login_succeeded" in message and "page_view" in message for message in records)
    assert any("Telemetry events stored: 3" in message for message in records)


def test_ingest_rejects_unknown_event_type_individually(client):
    response = client.post("/telemetry/events", json={"events": [make_event(event_type="nope")]})
    assert_counts(response, received=1, stored=0, rejected=1)


def test_ingest_rejects_missing_envelope_field_individually(client):
    event = make_event()
    del event["session_id"]
    response = client.post("/telemetry/events", json={"events": [event]})
    assert_counts(response, received=1, stored=0, rejected=1)


def test_ingest_rejects_invalid_event_id_individually(client):
    response = client.post(
        "/telemetry/events", json={"events": [make_event(event_id="not-a-uuid")]}
    )
    assert_counts(response, received=1, stored=0, rejected=1)


def test_ingest_rejects_invalid_schema_version_individually(client):
    response = client.post(
        "/telemetry/events", json={"events": [make_event(schema_version="v1")]}
    )
    assert_counts(response, received=1, stored=0, rejected=1)


def test_ingest_rejects_invalid_timestamp_individually(client):
    response = client.post(
        "/telemetry/events", json={"events": [make_event(timestamp="ayer")]}
    )
    assert_counts(response, received=1, stored=0, rejected=1)


def test_ingest_rejects_non_object_events_individually(client):
    response = client.post("/telemetry/events", json={"events": [1, "nope", None]})
    assert_counts(response, received=3, stored=0, rejected=3)


def test_ingest_rejects_unparseable_envelope(client):
    response = client.post("/telemetry/events", json={"events": "not-a-list"})
    assert response.status_code == 422


@pytest.mark.parametrize("source,app", [("frontend", "backoffice"), ("backend", "website")])
def test_ingest_accepts_source_and_app_combinations(client, source, app):
    response = client.post(
        "/telemetry/events",
        json={"events": [make_event(source=source, app=app)]},
    )
    assert_counts(response, received=1, stored=1, rejected=0)


def test_ingest_accepts_null_user_and_request_id(client):
    event = make_event(user_id=None, request_id=None)
    response = client.post("/telemetry/events", json={"events": [event]})
    assert_counts(response, received=1, stored=1, rejected=0)


def test_ingest_rejects_unknown_source_individually(client):
    response = client.post(
        "/telemetry/events", json={"events": [make_event(source="cli")]}
    )
    assert_counts(response, received=1, stored=0, rejected=1)
