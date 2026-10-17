import json
from pathlib import Path

from app.telemetry.catalog import (
    CONSENT_REQUIRED_EVENTS,
    EVENT_METADATA,
    HIGH_FREQUENCY_EVENTS,
    KNOWN_EVENT_TYPES,
)

SCHEMAS_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "telemetry" / "event-schemas.json"
)


def load_schemas() -> dict:
    return json.loads(SCHEMAS_PATH.read_text(encoding="utf-8"))


def test_catalog_covers_the_same_events_as_the_schema():
    events = load_schemas()["events"]
    assert set(events) == set(EVENT_METADATA)
    assert set(events) == set(KNOWN_EVENT_TYPES)


def test_allowlists_match_the_schema():
    events = load_schemas()["events"]
    for event_type, metadata in EVENT_METADATA.items():
        schema_properties = events[event_type]["allowlist"].get("properties", {})
        assert set(metadata["allowlist"]) == set(schema_properties), event_type


def test_required_properties_match_the_schema():
    events = load_schemas()["events"]
    for event_type, metadata in EVENT_METADATA.items():
        assert set(metadata["required_properties"]) == set(
            events[event_type]["required_properties"]
        ), event_type


def test_source_processing_and_frequency_match_the_schema():
    events = load_schemas()["events"]
    for event_type, metadata in EVENT_METADATA.items():
        schema = events[event_type]
        assert metadata["source"] == schema["source"], event_type
        assert metadata["processing"] == schema["processing"], event_type
        assert metadata["high_frequency"] == schema.get("high_frequency", False), event_type


def test_high_frequency_set_matches_the_schema():
    events = load_schemas()["events"]
    expected = {
        event_type
        for event_type, schema in events.items()
        if schema.get("high_frequency", False)
    }
    assert HIGH_FREQUENCY_EVENTS == expected


def test_consent_required_events_are_known_and_frontend():
    for event_type in CONSENT_REQUIRED_EVENTS:
        assert event_type in EVENT_METADATA, event_type
        assert EVENT_METADATA[event_type]["source"] == "frontend", event_type
