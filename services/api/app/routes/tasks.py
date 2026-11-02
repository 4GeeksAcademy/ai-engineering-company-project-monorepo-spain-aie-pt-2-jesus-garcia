"""Consulta del estado de las tareas asíncronas."""

from celery.result import AsyncResult
from fastapi import APIRouter, Depends

from app.core.dependencies import require_manager
from celery_app import celery_app
from schemas import TaskStatusResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Estados reales de Celery -> contrato público de cuatro estados.
_STATE_MAP = {
    "PENDING": "pending",
    "RECEIVED": "pending",
    "STARTED": "started",
    "RETRY": "started",
    "SUCCESS": "success",
    "FAILURE": "failure",
    "REVOKED": "failure",
}


@router.get(
    "/{task_id}",
    response_model=TaskStatusResponse,
    summary="Estado actual de una tarea y su resultado cuando está disponible",
)
def get_task_status(
    task_id: str,
    _=Depends(require_manager),
) -> TaskStatusResponse:
    result = AsyncResult(task_id, app=celery_app)
    state = result.state
    status = _STATE_MAP.get(state, "pending")

    payload = None
    if state == "SUCCESS":
        payload = result.result
    elif state in {"FAILURE", "REVOKED"}:
        payload = str(result.result) if result.result is not None else "Task failed"

    return TaskStatusResponse(
        task_id=task_id,
        status=status,
        result=payload,
    )
