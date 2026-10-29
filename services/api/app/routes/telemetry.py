import logging
import os

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.telemetry.ingest import ingest_batch
from database import get_db
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
    summary="Recibir y persistir un lote de eventos de telemetría",
)
def ingest_events(
    payload: TelemetryBatch,
    request: Request,
    session: Session = Depends(get_db),
) -> TelemetryIngestResponse:
    logger.info("Telemetry events received: %d", len(payload.events))

    result = ingest_batch(
        payload.events,
        environment=_resolve_environment(request),
        consent=_resolve_consent(request),
        allow_non_production=_allow_non_production(),
        session=session,
    )

    return TelemetryIngestResponse(
        received=result.received,
        stored=result.stored,
        rejected=result.rejected,
    )
