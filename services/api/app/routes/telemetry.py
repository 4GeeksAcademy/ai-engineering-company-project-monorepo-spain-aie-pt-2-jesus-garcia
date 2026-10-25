from datetime import datetime, timedelta, timezone
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session

from app.core.cache import cache, cached
from app.telemetry import analysis
from app.telemetry.ingest import ingest_batch
from database import get_db
from schemas import (
    TelemetryBatch,
    TelemetryIngestResponse,
    TelemetryReportResponse,
)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

logger = logging.getLogger("api.telemetry")

REPORT_CACHE_TTL = 60.0
DEFAULT_REPORT_WINDOW = timedelta(days=7)


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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_period(
    start_date: datetime | None,
    end_date: datetime | None,
) -> tuple[datetime, datetime]:
    """Resolve optional bounds into an explicit UTC period.

    The default window is the last seven days. ``now`` is truncated to the
    minute so repeated default requests share a cache entry during the TTL.
    """

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    resolved_end = _as_utc(end_date) if end_date else now
    resolved_start = (
        _as_utc(start_date)
        if start_date
        else resolved_end - DEFAULT_REPORT_WINDOW
    )

    if resolved_start >= resolved_end:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before end_date",
        )
    return resolved_start, resolved_end


def _report_cache_key(start_date: datetime, end_date: datetime) -> str:
    return f"telemetry:report:{start_date.isoformat()}:{end_date.isoformat()}"


@router.get(
    "/report",
    response_model=TelemetryReportResponse,
    summary="Métricas operativas de telemetría agregadas por día",
)
def telemetry_report(
    start_date: datetime | None = Query(
        default=None,
        description="Inicio del periodo (ISO 8601, UTC). Por defecto, now − 7 días.",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="Fin del periodo, exclusivo (ISO 8601, UTC). Por defecto, now.",
    ),
    session: Session = Depends(get_db),
) -> TelemetryReportResponse:
    resolved_start, resolved_end = _resolve_period(start_date, end_date)

    metrics = cached(
        cache,
        _report_cache_key(resolved_start, resolved_end),
        REPORT_CACHE_TTL,
        lambda: analysis.build_metrics(session, resolved_start, resolved_end),
    )

    return TelemetryReportResponse.model_validate(
        {
            "period": {"from": resolved_start, "to": resolved_end},
            "metrics": metrics,
        }
    )
