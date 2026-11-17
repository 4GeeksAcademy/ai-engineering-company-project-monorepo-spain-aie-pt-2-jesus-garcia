"""Servicio y repositorio SQL de la generación de propuestas (Parte 2)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
import sys

# El worker Celery arranca desde ``services/api`` (local) o ``/app`` (Docker).
# El paquete ``data`` vive en la raíz del monorepo; en Docker está montado como
# ``/app/data``. Se añade esa raíz antes de importar el pipeline.
for _parent in Path(__file__).resolve().parents:
    if (_parent / "data" / "pipelines").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from fastapi import HTTPException
from sqlmodel import Session, select

from data.pipelines.rfp_intake.catalog import DEPARTMENTS, DEPARTMENT_ORDER
from data.pipelines.rfp_intake.repository import TicketNotFoundError
from data.pipelines.rfp_proposal.handoff import (
    SECTION_NEEDS_REVIEW,
    SECTION_PASSED,
)
from models import (
    RFP_SECTION_EVALUATING,
    RFP_SECTION_GENERATING,
    RFP_SECTION_NEEDS_REVIEW,
    RFP_SECTION_PASSED,
    RFP_STATUS_ANALYZING,
    RFP_STATUS_AWAITING_APPROVAL,
    RFP_STATUS_COMPLETE,
    RFP_STATUS_DRAFTING,
    RFP_STATUS_EVALUATING,
    RFP_STATUS_NEEDS_REVIEW,
    RfpDepartmentSection,
    RfpMetadata,
    RfpSectionEvaluation,
    RfpTicket,
)
from schemas import RfpProposalRead, RfpProposalSectionRead

logger = logging.getLogger(__name__)

# Orden de avance del ticket. Solo se permite avanzar salvo ``force=True``.
STATUS_ORDER: dict[str, int] = {
    RFP_STATUS_ANALYZING: 0,
    RFP_STATUS_COMPLETE: 1,
    RFP_STATUS_DRAFTING: 2,
    RFP_STATUS_EVALUATING: 3,
    RFP_STATUS_NEEDS_REVIEW: 4,
    RFP_STATUS_AWAITING_APPROVAL: 5,
}

SECTION_ORDER = DEPARTMENT_ORDER


def _synchronized(method):
    """Serializa la sesión: LangGraph ejecuta departamentos en paralelo."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class SqlRfpProposalRepository:
    """Implementación PostgreSQL/SQLite del puerto ``ProposalRepository``."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._lock = threading.RLock()

    def _ticket(self, ticket_id: str) -> RfpTicket:
        ticket = self.session.get(RfpTicket, ticket_id)
        if ticket is None:
            raise TicketNotFoundError(f"Ticket {ticket_id} no encontrado.")
        return ticket

    def _touch(self, ticket: RfpTicket) -> None:
        ticket.updated_at = datetime.now(timezone.utc)

    @_synchronized
    def get_ticket(self, ticket_id: str) -> dict:
        ticket = self._ticket(ticket_id)
        return {
            "ticket_id": ticket.id,
            "rfp_id": ticket.rfp_id,
            "status": ticket.status,
            "handoff_status": ticket.handoff_status,
            "handoff_payload": ticket.handoff_payload,
            "proposal_status": ticket.proposal_status,
            "proposal_stage": ticket.proposal_stage,
        }

    @_synchronized
    def get_rfp_facts(self, ticket_id: str) -> dict:
        row = self.session.exec(
            select(RfpMetadata).where(RfpMetadata.ticket_id == ticket_id)
        ).first()
        if row is None:
            return {}
        extraction = row.extraction or {}
        return {
            "monthly_volume": row.monthly_volume,
            "sku_count": extraction.get("sku_count"),
            "return_volume": extraction.get("return_volume"),
            "return_rate": extraction.get("return_rate"),
            "deadline": row.deadline.isoformat() if row.deadline else None,
            "budget_range": row.budget_range,
        }

    @_synchronized
    def set_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        stage: str | None = None,
        force: bool = False,
    ) -> None:
        ticket = self._ticket(ticket_id)
        current = ticket.status
        if not force and STATUS_ORDER.get(status, 0) < STATUS_ORDER.get(current, 0):
            return
        ticket.status = status
        ticket.proposal_status = status
        if stage:
            ticket.proposal_stage = stage
        if status == RFP_STATUS_DRAFTING:
            ticket.error_message = None
            ticket.proposal_error = None
        self._touch(ticket)
        self.session.add(ticket)
        self.session.commit()

    def _section(self, ticket_id: str, department_id: str) -> RfpDepartmentSection:
        row = self.session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id,
                RfpDepartmentSection.department_id == department_id,
            )
        ).first()
        if row is None:
            row = RfpDepartmentSection(
                ticket_id=ticket_id,
                department_id=department_id,
                responsible=DEPARTMENTS.get(department_id, {}).get("responsible"),
            )
            self.session.add(row)
            self.session.commit()
            self.session.refresh(row)
        return row

    @_synchronized
    def save_draft(
        self,
        ticket_id: str,
        *,
        department_id: str,
        draft: dict,
        iteration: int,
    ) -> None:
        row = self._section(ticket_id, department_id)
        row.draft_content = draft.get("body_markdown")
        row.draft_payload = draft
        row.iteration_count = max(int(row.iteration_count or 0), iteration)
        row.generation_status = RFP_SECTION_GENERATING
        row.needs_human_review = False
        row.review_reason = None
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()

    @_synchronized
    def save_evaluation(
        self,
        ticket_id: str,
        *,
        department_id: str,
        evaluation: dict,
    ) -> None:
        row = self._section(ticket_id, department_id)
        row.evaluation_results = evaluation
        row.iteration_count = int(evaluation.get("iteration") or 1)
        row.last_feedback = evaluation.get("feedback_for_generator") or None
        row.generation_status = (
            RFP_SECTION_PASSED
            if evaluation.get("overall_pass")
            else RFP_SECTION_EVALUATING
        )

        history = self.session.exec(
            select(RfpSectionEvaluation).where(
                RfpSectionEvaluation.ticket_id == ticket_id,
                RfpSectionEvaluation.department_id == department_id,
                RfpSectionEvaluation.iteration == row.iteration_count,
            )
        ).first()
        if history is None:
            history = RfpSectionEvaluation(
                ticket_id=ticket_id,
                department_id=department_id,
                iteration=row.iteration_count,
            )
        history.overall_pass = bool(evaluation.get("overall_pass"))
        history.readability = evaluation.get("readability") or {}
        history.relevance = evaluation.get("relevance") or {}
        history.compliance = evaluation.get("compliance") or {}
        history.feedback = evaluation.get("feedback_for_generator") or None
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.add(history)
        self.session.commit()

    @_synchronized
    def save_section_status(
        self,
        ticket_id: str,
        *,
        department_id: str,
        status: str,
        review_reason: str | None = None,
    ) -> None:
        row = self._section(ticket_id, department_id)
        row.generation_status = status
        if status == RFP_SECTION_NEEDS_REVIEW or status == SECTION_NEEDS_REVIEW:
            row.needs_human_review = True
            row.review_reason = review_reason
        elif status == RFP_SECTION_PASSED or status == SECTION_PASSED:
            row.needs_human_review = False
            row.review_reason = None
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()

    @_synchronized
    def complete_proposal(
        self,
        ticket_id: str,
        *,
        handoff: dict,
        status: str,
    ) -> None:
        ticket = self._ticket(ticket_id)
        ticket.status = status
        ticket.proposal_status = status
        ticket.proposal_payload = handoff
        ticket.proposal_ready_at = datetime.now(timezone.utc)
        ticket.proposal_stage = status
        ticket.proposal_error = None
        ticket.error_message = None
        # Una propuesta nueva invalida las aprobaciones de la ejecución anterior.
        ticket.approval_status = None
        ticket.approval_thread_id = None
        ticket.approval_task_id = None
        ticket.approval_completed_at = None
        ticket.approval_error = None
        for section in handoff.get("sections") or []:
            row = self.session.exec(
                select(RfpDepartmentSection).where(
                    RfpDepartmentSection.ticket_id == ticket_id,
                    RfpDepartmentSection.department_id
                    == section.get("department_id"),
                )
            ).first()
            if row is None:
                continue
            row.approval_status = section.get("approval_status")
            row.needs_human_review = bool(section.get("provisional"))
            row.approver = None
            row.approved_at = None
            row.approval_comment = None
            row.approval_decided_at = None
            row.approval_round = 0
            row.approval_interrupt_id = None
            row.approval_packet = None
            if section.get("provisional"):
                row.review_reason = section.get("review_reason")
            row.updated_at = datetime.now(timezone.utc)
            self.session.add(row)
        self._touch(ticket)
        self.session.add(ticket)
        self.session.commit()

    @_synchronized
    def fail(self, ticket_id: str, *, stage: str, error: str) -> None:
        ticket = self._ticket(ticket_id)
        ticket.status = "error"
        ticket.proposal_status = "error"
        ticket.proposal_stage = stage[:60]
        ticket.proposal_error = error[:2000]
        self._touch(ticket)
        self.session.add(ticket)
        self.session.commit()


def _proposal_section_read(row: RfpDepartmentSection) -> RfpProposalSectionRead:
    provisional = bool(row.needs_human_review)
    status = row.generation_status or (
        SECTION_NEEDS_REVIEW if provisional else "pendiente"
    )
    return RfpProposalSectionRead(
        section_id=f"{row.ticket_id}:{row.department_id}",
        department_id=row.department_id,
        department_label=DEPARTMENTS.get(row.department_id, {}).get("label"),
        responsible=row.responsible,
        status=status,
        provisional=provisional,
        iteration_count=row.iteration_count or 0,
        draft_content=row.draft_content,
        draft_payload=row.draft_payload,
        evaluation_results=row.evaluation_results,
        review_reason=row.review_reason,
        approval_status=row.approval_status,
        approver=row.approver,
    )


def get_proposal_detail(session: Session, ticket_id: str) -> RfpProposalRead:
    ticket = session.get(RfpTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    if ticket.proposal_payload:
        payload = dict(ticket.proposal_payload)
        sections = payload.get("sections") or []
        return RfpProposalRead(
            ticket_id=ticket.id,
            rfp_id=ticket.rfp_id,
            status=ticket.status,
            generated_at=payload.get("generated_at"),
            client=payload.get("client") or {},
            client_country=payload.get("client_country"),
            currency=payload.get("currency"),
            services_requested=list(payload.get("services_requested") or []),
            sections=[RfpProposalSectionRead(**section) for section in sections],
            needs_human_review_sections=list(
                payload.get("needs_human_review_sections") or []
            ),
            metrics=payload.get("metrics") or {},
            source_handoff=payload.get("source_handoff") or {},
        )

    metadata = session.exec(
        select(RfpMetadata).where(RfpMetadata.ticket_id == ticket.id)
    ).first()
    rows = list(
        session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket.id
            )
        ).all()
    )
    ordered = sorted(
        rows,
        key=lambda row: (
            SECTION_ORDER.index(row.department_id)
            if row.department_id in SECTION_ORDER
            else len(SECTION_ORDER)
        ),
    )
    if not ordered:
        raise HTTPException(
            status_code=404,
            detail="El ticket todavía no tiene una propuesta generada.",
        )

    sections = [_proposal_section_read(row) for row in ordered]
    iterations = [section.iteration_count for section in sections]
    return RfpProposalRead(
        ticket_id=ticket.id,
        rfp_id=ticket.rfp_id,
        status=ticket.status,
        generated_at=None,
        client={
            "name": metadata.client_name if metadata else None,
            "contact": (metadata.extraction or {}).get("contact", {})
            if metadata
            else {},
        },
        client_country=metadata.client_country if metadata else None,
        currency=metadata.currency if metadata else None,
        services_requested=list(metadata.services_requested or [])
        if metadata
        else [],
        sections=sections,
        needs_human_review_sections=[
            section.department_id for section in sections if section.provisional
        ],
        metrics={
            "sections": len(sections),
            "average_iterations": (
                round(sum(iterations) / len(iterations), 2) if iterations else 0.0
            ),
            "max_iterations_used": max(iterations) if iterations else 0,
        },
        source_handoff={"handoff_ready": ticket.handoff_status == "ready"},
    )


__all__ = [
    "SqlRfpProposalRepository",
    "TicketNotFoundError",
    "get_proposal_detail",
]
