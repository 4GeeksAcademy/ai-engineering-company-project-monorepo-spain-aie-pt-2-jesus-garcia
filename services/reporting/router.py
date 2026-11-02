from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.core.cache import cache
from app.core.dependencies import require_manager
from database import get_db

from . import prefect_client, service
from .schemas import (
    PipelineRunLatest,
    PipelineRunTriggerRequest,
    PipelineRunTriggerResponse,
    WeeklyPerformanceResponse,
)

router = APIRouter(prefix="/reporting", tags=["reporting"])

WEEKLY_TTL = 60.0
LATEST_TTL = 5.0


@router.get(
    "/weekly-warehouse-client-performance",
    response_model=WeeklyPerformanceResponse,
    summary="Reporte semanal por almacén y cliente",
)
def weekly_warehouse_client_performance(
    week_start: date | None = Query(
        default=None,
        description="Lunes ISO de la semana; por defecto, la última calculada.",
    ),
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> WeeklyPerformanceResponse:
    key = f"reporting:weekly:{week_start.isoformat() if week_start else 'latest'}"
    hit = cache.get(key)
    if hit is not None:
        return hit

    try:
        result = service.get_weekly_performance(session, week_start)
    except service.ReportNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    cache.set(key, result, ttl=WEEKLY_TTL)
    return result


@router.get(
    "/pipeline-runs/latest",
    response_model=PipelineRunLatest,
    summary="Última corrida del pipeline (ledger, no Prefect)",
)
def latest_pipeline_run(
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> PipelineRunLatest:
    key = "reporting:latest"
    hit = cache.get(key)
    if hit is not None:
        return hit

    try:
        result = service.get_latest_pipeline_run(session)
    except service.ReportNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    cache.set(key, result, ttl=LATEST_TTL)
    return result


@router.post(
    "/pipeline-runs",
    response_model=PipelineRunTriggerResponse,
    status_code=202,
    summary="Dispara una corrida manual del pipeline",
)
def trigger_pipeline_run(
    payload: PipelineRunTriggerRequest | None = None,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> PipelineRunTriggerResponse:
    week_start = payload.week_start if payload else None
    lookback_weeks = payload.lookback_weeks if payload else None

    if service.has_running_run(session, week_start):
        raise HTTPException(
            status_code=409,
            detail="Ya hay una corrida en curso para esa semana.",
        )

    try:
        result = prefect_client.trigger_weekly_flow(week_start, lookback_weeks)
    except prefect_client.PrefectUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Prefect no disponible: {exc}",
        ) from exc

    cache.delete("reporting:latest")
    cache.delete_prefix("reporting:weekly:")
    return PipelineRunTriggerResponse(**result)
