"""Tarea Celery que ejecuta el pipeline de recepción de una RFP."""

from __future__ import annotations

import logging
import os

from sqlmodel import Session

from celery_app import celery_app
from database import engine

from ..services.rfp_service import SqlRfpRepository
from .dlq import record_dead_letter

logger = logging.getLogger("api.tasks.rfp_intake")

RETRY_BACKOFF_SECONDS = float(os.getenv("CELERY_RETRY_BACKOFF_SECONDS", "5"))

def _mark_ticket_error(ticket_id: str, error: str) -> None:
    """Garantiza que un fallo definitivo no deje el ticket en ``analizando``."""

    if engine is None:
        return
    try:
        with Session(engine) as session:
            from ..services.rfp_service import SqlRfpRepository

            repo = SqlRfpRepository(session)
            try:
                stage = repo.get_ticket(ticket_id).get("pipeline_stage") or "error"
            except Exception:
                stage = "error"
            repo.fail(ticket_id, stage=stage, error=error)
    except Exception:  # pragma: no cover - no ocultar el error original
        logger.exception("No se pudo marcar el ticket %s como error", ticket_id)


@celery_app.task(bind=True, name="rfp_intake.process_ticket", max_retries=2)
def process_rfp_ticket(self, ticket_id: str) -> dict:
    """Procesa una RFP en background y devuelve un resumen serializable."""

    task_id = self.request.id or ""
    attempt = self.request.retries + 1
    logger.info(
        "task_id=%s attempt=%d status=started ticket_id=%s",
        task_id,
        attempt,
        ticket_id,
    )

    if engine is None:
        raise RuntimeError(
            "DATABASE_URL no está configurada: no se puede procesar la RFP."
        )

    try:
        from data.pipelines.rfp_intake import run_rfp_intake

        with Session(engine) as session:
            repo = SqlRfpRepository(session)
            result = run_rfp_intake(ticket_id, repo)
    except Exception as exc:
        logger.exception(
            "task_id=%s attempt=%d status=failed ticket_id=%s error=%s",
            task_id,
            attempt,
            ticket_id,
            exc,
        )
        if self.request.retries < self.max_retries:
            countdown = RETRY_BACKOFF_SECONDS * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        message = f"{type(exc).__name__}: {exc}"
        _mark_ticket_error(ticket_id, message)
        record_dead_letter(
            task_id=task_id,
            task_name=self.name,
            attempts=attempt,
            max_retries=self.max_retries,
            error_message=message,
        )
        raise

    logger.info(
        "task_id=%s attempt=%d status=success ticket_id=%s status=%s",
        task_id,
        attempt,
        ticket_id,
        result.get("status"),
    )
    return {
        "ticket_id": ticket_id,
        "status": result.get("status"),
        "stage": result.get("stage"),
        "handoff_status": "ready" if result.get("status") == "completed" else "none",
    }
