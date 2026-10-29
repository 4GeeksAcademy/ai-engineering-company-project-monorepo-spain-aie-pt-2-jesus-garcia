from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, delete, select

from database import engine
from models import TelemetryEventRecord


@pytest.fixture(autouse=True)
def _clean_telemetry_events():
    SQLModel.metadata.create_all(engine)

    def clear() -> None:
        with Session(engine) as session:
            session.exec(delete(TelemetryEventRecord))
            session.commit()

    clear()
    yield
    clear()


def make_event(**overrides) -> dict:
    event = {
        "event_id": str(uuid4()),
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
    event.update(overrides)
    return event


def post_events(client, events, **kwargs):
    return client.post("/telemetry/events", json={"events": events}, **kwargs)


def stored_rows() -> list[TelemetryEventRecord]:
    with Session(engine) as session:
        return list(session.exec(select(TelemetryEventRecord)).all())


def test_valid_batch_is_persisted_with_fixed_columns_and_tags(client):
    response = post_events(client, [make_event(), make_event(event_type="outbound_order_created")])

    assert response.status_code == 200
    assert response.json() == {"received": 2, "stored": 2, "rejected": 0}

    rows = stored_rows()
    assert len(rows) == 2
    row = next(r for r in rows if r.event_type == "inbound_order_created")
    assert row.service == "backoffice"
    assert row.source == "backend"
    assert row.session_id == "session-abc"
    assert row.user_id == "1"
    assert row.request_id == "req-1"
    assert row.schema_version == "1.0.0"
    assert row.tags == {
        "warehouse": "los_angeles",
        "client_id": "fashion-co",
        "product_id": "CLT-SNK-W-42",
        "product_category": "fashion",
        "quantity": 20,
    }
    assert row.received_at is not None


def test_timestamp_from_envelope_is_stored_but_not_replaced_by_now(client):
    post_events(client, [make_event(timestamp="2026-10-05T20:34:00.000Z")])

    row = stored_rows()[0]
    assert row.timestamp.replace(tzinfo=None) == datetime(2026, 10, 5, 20, 34)


def test_service_is_derived_from_app(client):
    post_events(client, [make_event(app="website")])
    assert stored_rows()[0].service == "website"


def test_mixed_batch_stores_only_valid_events(client):
    missing_session = make_event()
    del missing_session["session_id"]

    events = [
        make_event(),
        make_event(event_id="not-a-uuid"),
        make_event(event_type="unknown_event"),
        missing_session,
    ]
    response = post_events(client, events)

    assert response.json() == {"received": 4, "stored": 1, "rejected": 3}
    rows = stored_rows()
    assert len(rows) == 1
    assert rows[0].event_type == "inbound_order_created"


def test_non_object_items_are_rejected_without_stopping_the_batch(client):
    response = post_events(client, [make_event(), "nope", 42, None])

    assert response.json() == {"received": 4, "stored": 1, "rejected": 3}
    assert len(stored_rows()) == 1


def test_unparseable_envelope_returns_422_and_stores_nothing(client):
    response = client.post("/telemetry/events", json={"events": "not-a-list"})

    assert response.status_code == 422
    assert stored_rows() == []


def test_tags_only_keep_allowlisted_properties(client):
    post_events(
        client,
        [
            make_event(
                properties={
                    "warehouse": "zaragoza",
                    "client_id": "electro-brand",
                    "product_id": "AUR-BT-01",
                    "product_category": "electronics",
                    "quantity": 5,
                    "password": "hunter2",
                    "secret_note": "should-not-be-stored",
                }
            )
        ],
    )

    tags = stored_rows()[0].tags
    assert set(tags) == {
        "warehouse",
        "client_id",
        "product_id",
        "product_category",
        "quantity",
    }
    assert tags["client_id"] == "electro-brand"


def test_tags_are_sanitized_inside_allowed_keys(client):
    post_events(
        client,
        [
            make_event(
                event_type="login_failed",
                source="frontend",
                properties={
                    "failure_reason": "contact ana@trackflow.com",
                    "method": "password",
                },
            )
        ],
    )

    assert stored_rows()[0].tags == {
        "failure_reason": "contact [redacted-email]",
        "method": "password",
    }


def test_empty_properties_are_stored_as_empty_object(client):
    post_events(
        client,
        [make_event(event_type="login_failed", source="frontend", properties={})],
    )

    assert stored_rows()[0].tags == {}


def test_duplicate_event_id_inside_batch_is_stored_once(client):
    event = make_event()
    duplicate = {**event, "properties": {**event["properties"], "quantity": 999}}

    response = post_events(client, [event, duplicate])

    assert response.json() == {"received": 2, "stored": 1, "rejected": 1}
    rows = stored_rows()
    assert len(rows) == 1
    assert rows[0].tags["quantity"] == 20


def test_retried_event_id_is_idempotent_across_requests(client):
    event = make_event()

    first = post_events(client, [event])
    second = post_events(client, [event])

    assert first.json() == {"received": 1, "stored": 1, "rejected": 0}
    assert second.json() == {"received": 1, "stored": 0, "rejected": 1}
    assert len(stored_rows()) == 1


def test_batch_is_written_with_a_single_insert_statement(client):
    insert_statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        normalized = statement.lstrip().upper()
        if normalized.startswith("INSERT INTO TELEMETRY_EVENTS"):
            insert_statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        response = post_events(client, [make_event() for _ in range(20)])
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert response.json() == {"received": 20, "stored": 20, "rejected": 0}
    assert len(stored_rows()) == 20
    assert len(insert_statements) == 1


def test_nullable_fields_normalize_blank_values_to_null(client):
    post_events(client, [make_event(user_id="", request_id="   ")])

    row = stored_rows()[0]
    assert row.user_id is None
    assert row.request_id is None


def test_environment_gate_prevents_storage(client):
    response = post_events(
        client,
        [make_event(event_type="login_failed", source="frontend", properties={"failure_reason": "x"})],
        headers={"X-Telemetry-Environment": "development"},
    )

    assert response.json() == {"received": 1, "stored": 0, "rejected": 1}
    assert stored_rows() == []


def test_environment_gate_can_be_overridden(client, monkeypatch):
    monkeypatch.setenv("TELEMETRY_ALLOW_NON_PRODUCTION", "1")

    response = post_events(
        client,
        [make_event(event_type="login_failed", source="frontend", properties={"failure_reason": "x"})],
        headers={"X-Telemetry-Environment": "development"},
    )

    assert response.json() == {"received": 1, "stored": 1, "rejected": 0}
    assert len(stored_rows()) == 1


def test_consent_gate_prevents_storage_of_analytics_events(client):
    response = post_events(
        client,
        [make_event(event_type="page_view", source="frontend", properties={"path": "/", "app": "backoffice"})],
        headers={"X-Telemetry-Consent": "denied"},
    )

    assert response.json() == {"received": 1, "stored": 0, "rejected": 1}
    assert stored_rows() == []
