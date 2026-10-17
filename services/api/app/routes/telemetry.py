import logging
import os

from fastapi import APIRouter, Request

from app.telemetry.barriers import process_events
from schemas import TelemetryBatch, TelemetryIngestResponse

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

logger = logging.getLogger("api.telemetry")


def _resolve_environment(request: Request) -> str:
    return (
        request.headers.get("x-telemetry-environment")
        or request.query_params.get("environment")
        or "production"
    )


def _resolve_consent(request: Request) -> str:
    return (
        request.headers.get("x-telemetry-consent")
        or request.query_params.get("consent")
        or "unset"
    )


def _allow_non_production() -> bool:
    return os.getenv("TELEMETRY_ALLOW_NON_PRODUCTION") == "1"


@router.post(
    "/events",
    response_model=TelemetryIngestResponse,
    summary="Recibir un lote de eventos de telemetría",
)
def ingest_events(payload: TelemetryBatch, request: Request) -> TelemetryIngestResponse:
    received = payload.events
    received_counts = {}
    for event in received:
        key = event.event_type.value
        received_counts[key] = received_counts.get(key, 0) + 1
    logger.info(
        "Telemetry events received: %d | by_type: %s",
        len(received),
        received_counts,
    )

    accepted, accepted_counts, dropped_counts = process_events(
        received,
        environment=_resolve_environment(request),
        consent=_resolve_consent(request),
        allow_non_production=_allow_non_production(),
    )
    logger.info(
        "Telemetry events accepted: %d | dropped: %d | accepted_by_type: %s | dropped_by_type: %s",
        accepted,
        sum(dropped_counts.values()),
        dict(accepted_counts),
        dict(dropped_counts),
    )

    return TelemetryIngestResponse(received=len(received))
