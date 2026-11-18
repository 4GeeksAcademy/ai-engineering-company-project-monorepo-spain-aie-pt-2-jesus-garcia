"""Tareas Celery de la aprobación humana (Parte 3)."""

from __future__ import annotations

import logging
import os

from sqlmodel import Session

from celery_app import celery_app
from database import engine

from ..services.rfp_approval_service import (
    SqlRfpApprovalRepository,
    resume_department,
    start_approvals,
)
from schemas import RfpApprovalDecisionRequest
from .dlq import record_dead_letter

logger = logging.getLogger("api.tasks.rfp_approval")

RETRY_BACKOFF_SECONDS = float(os.getenv("CELERY_RETRY_BACKOFF_SECONDS", "5"))


def _mark_approval_error(ticket_id: str, stage: str, error: str) -> None:
    if engine is None:
        return
    try:
        with Session(engine) as session:
            repo = SqlRfpApprovalRepository(session)
            repo.fail(ticket_id, stage=stage, error=error)
    except Exception:  # pragma: no cover - no ocultar el error original
        logger.exception("No se pudo marcar el ticket %s con approval_error", ticket_id)


@celery_app.task(bind=True, name="rfp_approval.start_ticket", max_retries=2)
def start_ticket_approvals(self, ticket_id: str) -> dict:
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
            "DATABASE_URL no está configurada: no se puede iniciar la aprobación."
        )
    try:
        with Session(engine) as session:
            summary = start_approvals(session, ticket_id)
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
        _mark_approval_error(ticket_id, "inicio_aprobacion", message)
        record_dead_letter(
            task_id=task_id,
            task_name=self.name,
            attempts=attempt,
            max_retries=self.max_retries,
            error_message=message,
        )
        raise
    logger.info(
        "task_id=%s attempt=%d status=success ticket_id=%s pending=%d",
        task_id,
        attempt,
        ticket_id,
        len(summary.get("pending") or []),
    )
    return summary


@celery_app.task(bind=True, name="rfp_approval.resume_ticket", max_retries=2)
def resume_ticket_approval(
    self,
    ticket_id: str,
    department_id: str,
    decision: dict,
) -> dict:
    task_id = self.request.id or ""
    attempt = self.request.retries + 1
    logger.info(
        "task_id=%s attempt=%d status=started ticket_id=%s department=%s action=%s",
        task_id,
        attempt,
        ticket_id,
        department_id,
        (decision or {}).get("action"),
    )
    if engine is None:
        raise RuntimeError(
            "DATABASE_URL no está configurada: no se puede reanudar la aprobación."
        )
    try:
        request = RfpApprovalDecisionRequest(**decision)
        with Session(engine) as session:
            summary = resume_department(
                session, ticket_id, department_id, request
            )
    except Exception as exc:
        logger.exception(
            "task_id=%s attempt=%d status=failed ticket_id=%s department=%s error=%s",
            task_id,
            attempt,
            ticket_id,
            department_id,
            exc,
        )
        if self.request.retries < self.max_retries:
            countdown = RETRY_BACKOFF_SECONDS * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        message = f"{type(exc).__name__}: {exc}"
        _mark_approval_error(ticket_id, "reanudar_aprobacion", message)
        record_dead_letter(
            task_id=task_id,
            task_name=self.name,
            attempts=attempt,
            max_retries=self.max_retries,
            error_message=message,
        )
        raise
    logger.info(
        "task_id=%s attempt=%d status=success ticket_id=%s department=%s status=%s",
        task_id,
        attempt,
        ticket_id,
        department_id,
        summary.get("status"),
    )
    return summary
