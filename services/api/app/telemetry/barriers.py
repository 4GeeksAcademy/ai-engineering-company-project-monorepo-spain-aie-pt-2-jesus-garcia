from collections import Counter

from app.telemetry.catalog import get_allowlist, requires_consent
from app.telemetry.sanitize import sanitize_properties

NON_PRODUCTION_ENVIRONMENTS = frozenset({"development", "test"})


def is_blocked_environment(environment: str, allow_non_production: bool) -> bool:
    return environment in NON_PRODUCTION_ENVIRONMENTS and not allow_non_production


def filter_properties(event_type: str, properties: dict) -> dict:
    cleaned = sanitize_properties(properties)
    allowed = set(get_allowlist(event_type))
    return {key: value for key, value in cleaned.items() if key in allowed}


def process_events(events, environment: str, consent: str, allow_non_production: bool):
    environment_blocked = is_blocked_environment(environment, allow_non_production)
    accepted_counts: Counter = Counter()
    dropped_counts: Counter = Counter()
    accepted = 0

    for event in events:
        event_type = event.event_type.value
        if environment_blocked:
            dropped_counts[event_type] += 1
            continue
        if requires_consent(event_type) and consent != "granted":
            dropped_counts[event_type] += 1
            continue
        event.properties = filter_properties(event_type, event.properties)
        accepted += 1
        accepted_counts[event_type] += 1

    return accepted, accepted_counts, dropped_counts
