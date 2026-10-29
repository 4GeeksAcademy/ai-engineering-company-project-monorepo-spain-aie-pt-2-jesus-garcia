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


def apply_barriers(
    events,
    environment: str,
    consent: str,
    allow_non_production: bool,
):
    """Aplica entorno + consentimiento + limpieza/allowlist a eventos ya validados.

    Devuelve los eventos que pueden persistirse (mutados con `properties`
    filtradas) y contadores por tipo para el log.
    """

    environment_blocked = is_blocked_environment(environment, allow_non_production)
    accepted_events = []
    accepted_counts: Counter = Counter()
    dropped_counts: Counter = Counter()
    drop_reasons: Counter = Counter()

    for event in events:
        event_type = event.event_type.value
        if environment_blocked:
            dropped_counts[event_type] += 1
            drop_reasons["environment"] += 1
            continue
        if requires_consent(event_type) and consent != "granted":
            dropped_counts[event_type] += 1
            drop_reasons["consent"] += 1
            continue
        event.properties = filter_properties(event_type, event.properties)
        accepted_events.append(event)
        accepted_counts[event_type] += 1

    return accepted_events, accepted_counts, dropped_counts, drop_reasons


def process_events(events, environment: str, consent: str, allow_non_production: bool):
    """Wrapper con la firma histórica (contadores) usado por los tests existentes."""

    accepted_events, accepted_counts, dropped_counts, _ = apply_barriers(
        events,
        environment=environment,
        consent=consent,
        allow_non_production=allow_non_production,
    )
    return len(accepted_events), accepted_counts, dropped_counts
