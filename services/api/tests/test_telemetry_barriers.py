import logging
from uuid import uuid4

from app.telemetry.barriers import filter_properties, is_blocked_environment, process_events
from app.telemetry.sanitize import sanitize_properties
from models import TelemetryEvent


def make_model_event(event_type: str, properties: dict | None = None) -> TelemetryEvent:
    return TelemetryEvent(
        event_id=str(uuid4()),
        timestamp="2026-01-01T00:00:00.000Z",
        session_id="s1",
        user_id=None,
        event_type=event_type,
        schema_version="1.0.0",
        request_id=None,
        source="frontend",
        app="backoffice",
        properties=properties or {},
    )


def make_payload_event(event_type: str, properties: dict | None = None) -> dict:
    return {
        "event_id": str(uuid4()),
        "timestamp": "2026-01-01T00:00:00.000Z",
        "session_id": "s1",
        "user_id": None,
        "event_type": event_type,
        "schema_version": "1.0.0",
        "request_id": None,
        "source": "frontend",
        "app": "backoffice",
        "properties": properties or {},
    }


def accepted_count(caplog) -> int | None:
    for record in caplog.records:
        message = record.getMessage()
        if message.startswith("Telemetry events accepted:"):
            return int(message.split("accepted:")[1].split("|")[0].strip())
    return None


def dropped_count(caplog) -> int | None:
    for record in caplog.records:
        message = record.getMessage()
        if message.startswith("Telemetry events accepted:"):
            return int(message.split("dropped:")[1].split("|")[0].strip())
    return None


def test_filter_properties_drops_unknown_keys_and_redacts():
    filtered = filter_properties(
        "login_failed",
        {
            "failure_reason": "contact ana@trackflow.com",
            "leaked": "should-be-dropped",
            "password": "hunter2",
        },
    )
    assert filtered == {"failure_reason": "contact [redacted-email]"}


def test_is_blocked_environment():
    assert is_blocked_environment("development", False) is True
    assert is_blocked_environment("test", False) is True
    assert is_blocked_environment("production", False) is False
    assert is_blocked_environment("development", True) is False


def test_process_events_blocks_analytics_without_consent():
    events = [
        make_model_event("page_view", {"path": "/", "app": "backoffice"}),
        make_model_event("login_failed", {"failure_reason": "invalid_credentials"}),
    ]
    accepted, accepted_counts, dropped_counts = process_events(
        events, environment="production", consent="denied", allow_non_production=False
    )
    assert accepted == 1
    assert accepted_counts["login_failed"] == 1
    assert dropped_counts["page_view"] == 1


def test_process_events_blocks_non_production_environment():
    events = [
        make_model_event("login_failed", {"failure_reason": "invalid_credentials"}),
    ]
    accepted, _, dropped_counts = process_events(
        events, environment="development", consent="granted", allow_non_production=False
    )
    assert accepted == 0
    assert dropped_counts["login_failed"] == 1


def test_process_events_allow_non_production_override():
    events = [make_model_event("login_failed", {"failure_reason": "invalid_credentials"})]
    accepted, _, _ = process_events(
        events, environment="development", consent="granted", allow_non_production=True
    )
    assert accepted == 1


def test_process_events_sanitizes_and_filters_properties():
    events = [
        make_model_event(
            "login_failed",
            {"failure_reason": "ana@trackflow.com", "leaked": "x"},
        )
    ]
    process_events(events, environment="production", consent="granted", allow_non_production=False)
    assert events[0].properties == {"failure_reason": "[redacted-email]"}


def test_sanitize_properties_drops_nested_sensitive_keys():
    cleaned = sanitize_properties({"nested": {"token": "abc", "ok": 1}})
    assert cleaned == {"nested": {"ok": 1}}


def test_endpoint_environment_gate_drops_dev_events(client, caplog):
    caplog.set_level(logging.INFO, logger="api.telemetry")
    payload = {"events": [make_payload_event("login_failed", {"failure_reason": "invalid_credentials"})]}
    response = client.post(
        "/telemetry/events",
        json=payload,
        headers={"X-Telemetry-Environment": "development"},
    )
    assert response.status_code == 200
    assert response.json() == {"received": 1}
    assert accepted_count(caplog) == 0
    assert dropped_count(caplog) == 1


def test_endpoint_consent_gate_drops_analytics_only(client, caplog):
    caplog.set_level(logging.INFO, logger="api.telemetry")
    payload = {
        "events": [
            make_payload_event("page_view", {"path": "/", "app": "backoffice"}),
            make_payload_event("login_failed", {"failure_reason": "invalid_credentials"}),
        ]
    }
    response = client.post(
        "/telemetry/events",
        json=payload,
        headers={
            "X-Telemetry-Environment": "production",
            "X-Telemetry-Consent": "denied",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"received": 2}
    assert accepted_count(caplog) == 1
    assert dropped_count(caplog) == 1


def test_endpoint_accepts_all_when_production_and_consent_granted(client, caplog):
    caplog.set_level(logging.INFO, logger="api.telemetry")
    payload = {
        "events": [
            make_payload_event("page_view", {"path": "/", "app": "backoffice"}),
            make_payload_event("login_failed", {"failure_reason": "invalid_credentials"}),
        ]
    }
    response = client.post(
        "/telemetry/events",
        json=payload,
        headers={
            "X-Telemetry-Environment": "production",
            "X-Telemetry-Consent": "granted",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"received": 2}
    assert accepted_count(caplog) == 2
    assert dropped_count(caplog) == 0


def test_endpoint_reads_environment_and_consent_from_query_params(client, caplog):
    caplog.set_level(logging.INFO, logger="api.telemetry")
    payload = {"events": [make_payload_event("page_view", {"path": "/", "app": "backoffice"})]}
    response = client.post(
        "/telemetry/events?environment=production&consent=granted",
        json=payload,
    )
    assert response.status_code == 200
    assert accepted_count(caplog) == 1
