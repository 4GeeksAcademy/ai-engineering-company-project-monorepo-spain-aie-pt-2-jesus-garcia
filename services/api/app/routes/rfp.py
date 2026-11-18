"""Router HTTP de recepción de RFPs (extiende el backend existente)."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlmodel import Session

from database import get_db
from models import (
    RFP_HANDOFF_READY,
    RFP_STATUS_ANALYZING,
    RFP_STATUS_AWAITING_APPROVAL,
    RFP_STATUS_COMPLETE,
    RFP_STATUS_DRAFTING,
    RFP_STATUS_ERROR,
    RFP_STATUS_EVALUATING,
    RFP_STATUS_FINISHED,
    RFP_STATUS_NEEDS_REVIEW,
    RfpTicket,
)
from schemas import (
    RfpApprovalDecisionRequest,
    RfpApprovalResumeResponse,
    RfpApprovalStartResponse,
    RfpApprovalsRead,
    RfpFinalDocumentRead,
    RfpProposalRead,
    RfpProposalStartResponse,
    RfpTicketListItem,
    RfpTicketRead,
    RfpTicketStatusRead,
    RfpTraceRead,
    RfpUploadResponse,
)
from app.core.dependencies import require_manager
from app.realtime.events import publish_rfp_ticket_created
from app.services.rfp_approval_service import (
    SqlRfpApprovalRepository,
    get_approvals,
    get_final_document,
    get_final_document_markdown,
    get_trace,
)
from app.services.rfp_proposal_service import get_proposal_detail
from app.services.rfp_service import (
    MAX_UPLOAD_BYTES,
    RfpUploadError,
    create_ticket,
    get_ticket,
    get_ticket_detail,
    get_ticket_status,
    list_tickets,
    store_pdf_bytes,
)
from app.tasks.rfp_approval import (
    resume_ticket_approval,
    start_ticket_approvals,
)
from app.tasks.rfp_intake import process_rfp_ticket
from app.tasks.rfp_proposal import generate_proposal
from data.pipelines.rfp_approval.contracts import (
    ApprovalDecisionError,
    ApprovalStateError,
    validate_decision,
)
from data.pipelines.rfp_approval.runner import max_rounds_from_env
from data.pipelines.rfp_proposal.contract import (
    HandoffContractError,
    parse_intake_handoff,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rfp", tags=["rfp"])

ACTIVE_PROPOSAL_STATUSES = {RFP_STATUS_DRAFTING, RFP_STATUS_EVALUATING}
READY_PROPOSAL_STATUSES = {
    RFP_STATUS_COMPLETE,
    RFP_STATUS_NEEDS_REVIEW,
    RFP_STATUS_AWAITING_APPROVAL,
}


@router.post(
    "/tickets",
    response_model=RfpUploadResponse,
    status_code=202,
    summary="Subir un PDF y encolar el análisis de la RFP",
)
def upload_ticket(
    file: UploadFile = File(...),
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpUploadResponse:
    ticket_id = str(uuid4())
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    try:
        path, safe_name, digest = store_pdf_bytes(
            ticket_id, file.filename, content
        )
    except RfpUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ticket = create_ticket(
        session,
        filename=safe_name,
        pdf_path=path,
        file_sha256=digest,
    )

    try:
        async_result = process_rfp_ticket.delay(ticket.id)
        task_id = async_result.id
    except Exception as exc:  # pragma: no cover - broker caído
        logger.exception("No se pudo encolar el ticket %s", ticket.id)
        ticket.status = RFP_STATUS_ERROR
        ticket.error_message = f"No se pudo encolar el análisis: {exc}"[:2000]
        session.add(ticket)
        session.commit()
        raise HTTPException(
            status_code=503,
            detail=(
                "El PDF se guardó, pero no se pudo encolar el análisis. "
                f"Ticket {ticket.rfp_id}."
            ),
        ) from exc

    ticket.celery_task_id = task_id
    ticket.status = RFP_STATUS_ANALYZING
    ticket.pipeline_stage = "encolado"
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    logger.info(
        "rfp_upload ticket=%s rfp_id=%s task_id=%s file=%s",
        ticket.id,
        ticket.rfp_id,
        task_id,
        safe_name,
    )
    # Notificación en tiempo real: el ticket acaba de entrar al sistema con
    # status=analizando. Los metadatos de la RFP aún no existen; el pipeline
    # los publicará en `rfp_ticket_metadata_ready`.
    publish_rfp_ticket_created(ticket)
    return RfpUploadResponse(
        ticket_id=ticket.id,
        rfp_id=ticket.rfp_id,
        status=ticket.status,
        task_id=task_id,
    )


@router.get(
    "/tickets",
    response_model=list[RfpTicketListItem],
    summary="Listar tickets de recepción",
)
def list_rfp_tickets(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> list[RfpTicketListItem]:
    return list_tickets(
        session, status=status, limit=limit, offset=offset
    )


@router.get(
    "/tickets/{ticket_id}",
    response_model=RfpTicketRead,
    summary="Detalle de un ticket: metadatos, métricas y secciones",
)
def get_rfp_ticket(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpTicketRead:
    return get_ticket_detail(session, ticket_id)


@router.get(
    "/tickets/{ticket_id}/status",
    response_model=RfpTicketStatusRead,
    summary="Polling ligero del estado del ticket",
)
def get_rfp_ticket_status(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpTicketStatusRead:
    return get_ticket_status(session, ticket_id)


@router.get(
    "/handoff/{ticket_id}",
    response_model=dict,
    summary="Payload congelado para la Parte 2 (sin reparsear el PDF)",
)
def get_rfp_handoff(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> dict:
    ticket: RfpTicket = get_ticket(session, ticket_id)
    if not ticket.handoff_payload:
        raise HTTPException(
            status_code=409,
            detail="El ticket todavía no tiene un handoff disponible.",
        )
    return ticket.handoff_payload


@router.post(
    "/tickets/{ticket_id}/proposal",
    response_model=RfpProposalStartResponse,
    status_code=202,
    summary="Generar y evaluar la propuesta desde el handoff de la Parte 1",
)
def start_rfp_proposal(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpProposalStartResponse:
    ticket = get_ticket(session, ticket_id)

    if ticket.status == RFP_STATUS_FINISHED:
        raise HTTPException(
            status_code=409,
            detail="El ticket ya está terminado; no se puede regenerar la propuesta.",
        )
    if ticket.approval_status in {"pending", "resuming", "encolado"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "Hay un flujo de aprobaciones en curso: no se puede "
                "regenerar la propuesta."
            ),
        )
    if ticket.status in ACTIVE_PROPOSAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Ya hay una generación de propuesta en curso para este ticket.",
        )
    if ticket.proposal_status == "encolado":
        raise HTTPException(
            status_code=409,
            detail="La generación de propuesta ya está encolada para este ticket.",
        )
    if ticket.status not in READY_PROPOSAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                "El ticket no está listo para la Parte 2: debe estar en "
                "'analisis_completo' (o en revisión) con el handoff marcado "
                f"como listo. Estado actual: {ticket.status}."
            ),
        )
    if ticket.handoff_status != RFP_HANDOFF_READY:
        raise HTTPException(
            status_code=409,
            detail="El ticket todavía no tiene el handoff de la Parte 1.",
        )

    try:
        parse_intake_handoff(ticket.handoff_payload, ticket_id=ticket.id)
    except HandoffContractError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"El handoff de la Parte 1 no es válido: {exc}",
        ) from exc

    ticket.proposal_status = "encolado"
    ticket.proposal_stage = "encolado"
    ticket.proposal_error = None
    session.add(ticket)
    session.commit()

    try:
        async_result = generate_proposal.delay(ticket.id)
        task_id = async_result.id
    except Exception as exc:  # pragma: no cover - broker caído
        logger.exception("No se pudo encolar la propuesta %s", ticket.id)
        ticket.proposal_status = "error"
        ticket.proposal_error = f"No se pudo encolar la generación: {exc}"[:2000]
        session.add(ticket)
        session.commit()
        raise HTTPException(
            status_code=503,
            detail="No se pudo encolar la generación de la propuesta.",
        ) from exc

    ticket.proposal_task_id = task_id
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    logger.info(
        "rfp_proposal_enqueue ticket=%s rfp_id=%s task_id=%s",
        ticket.id,
        ticket.rfp_id,
        task_id,
    )
    return RfpProposalStartResponse(
        ticket_id=ticket.id,
        task_id=task_id,
        status=ticket.status,
    )


@router.get(
    "/tickets/{ticket_id}/proposal",
    response_model=RfpProposalRead,
    summary="Borradores, evaluaciones y estado de la propuesta",
)
def get_rfp_proposal(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpProposalRead:
    return get_proposal_detail(session, ticket_id)


# --- Hito 9, Parte 3 — aprobación humana y cierre ---------------------------


@router.post(
    "/tickets/{ticket_id}/approvals/start",
    response_model=RfpApprovalStartResponse,
    status_code=202,
    summary="Iniciar el flujo de aprobaciones por departamento",
)
def start_rfp_approvals(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpApprovalStartResponse:
    ticket = get_ticket(session, ticket_id)
    if ticket.status == RFP_STATUS_FINISHED:
        raise HTTPException(
            status_code=409, detail="El ticket ya está terminado."
        )
    if ticket.approval_status == "encolado":
        raise HTTPException(
            status_code=409,
            detail="El flujo de aprobaciones ya está iniciado para este ticket.",
        )
    if ticket.approval_status == "rejected":
        raise HTTPException(
            status_code=409,
            detail=(
                "La ejecución de aprobación terminó con rechazos. Regenera la "
                "propuesta (Parte 2) antes de iniciar un run nuevo."
            ),
        )
    recovery = False
    if ticket.approval_status in {"pending", "resuming"}:
        current = get_approvals(session, ticket_id)
        if current.pending:
            raise HTTPException(
                status_code=409,
                detail="El flujo de aprobaciones ya está iniciado para este ticket.",
            )
        recovery = True
    if not ticket.proposal_payload:
        raise HTTPException(
            status_code=409,
            detail="El ticket todavía no tiene una propuesta generada.",
        )
    if ticket.status not in {
        RFP_STATUS_AWAITING_APPROVAL,
        RFP_STATUS_NEEDS_REVIEW,
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "El ticket no está listo para aprobaciones: debe estar en "
                f"'esperando_aprobación' o 'needs_human_review'. Estado actual: "
                f"{ticket.status}."
            ),
        )

    ticket.approval_status = "resuming" if recovery else "encolado"
    ticket.approval_error = None
    session.add(ticket)
    session.commit()

    try:
        async_result = start_ticket_approvals.delay(ticket.id)
        task_id = async_result.id
    except Exception as exc:  # pragma: no cover - broker caído
        logger.exception("No se pudo encolar la aprobación %s", ticket.id)
        ticket.approval_status = None
        ticket.approval_error = f"No se pudo encolar: {exc}"[:2000]
        session.add(ticket)
        session.commit()
        raise HTTPException(
            status_code=503,
            detail="No se pudo encolar el flujo de aprobaciones.",
        ) from exc

    ticket.approval_task_id = task_id
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return RfpApprovalStartResponse(
        ticket_id=ticket.id, task_id=task_id, status=ticket.status
    )


@router.get(
    "/tickets/{ticket_id}/approvals",
    response_model=RfpApprovalsRead,
    summary="Aprobaciones pendientes y decisiones por departamento",
)
def get_rfp_approvals(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpApprovalsRead:
    return get_approvals(session, ticket_id)


@router.post(
    "/tickets/{ticket_id}/approvals/{department_id}",
    response_model=RfpApprovalResumeResponse,
    status_code=202,
    summary="Reanudar la rama de un departamento con una decisión humana",
)
def resume_rfp_approval(
    ticket_id: str,
    department_id: str,
    decision: RfpApprovalDecisionRequest,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpApprovalResumeResponse:
    ticket = get_ticket(session, ticket_id)
    if ticket.status != RFP_STATUS_AWAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=(
                "El ticket no está esperando aprobación "
                f"(status={ticket.status})."
            ),
        )
    repo = SqlRfpApprovalRepository(session)
    sections = repo.get_sections(ticket_id)
    section = sections.get(department_id)
    if section is None:
        raise HTTPException(
            status_code=404,
            detail=f"El departamento {department_id!r} no está activo.",
        )
    try:
        validate_decision(
            decision.model_dump(),
            section=section,
            max_rounds=max_rounds_from_env(),
        )
    except ApprovalDecisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    expected_interrupt = section.get("approval_interrupt_id")
    if not expected_interrupt:
        raise HTTPException(
            status_code=409,
            detail="La sección no tiene una aprobación pendiente.",
        )
    if decision.interrupt_id != expected_interrupt:
        raise HTTPException(
            status_code=409,
            detail="La decisión no corresponde al interrupt pendiente.",
        )

    ticket.approval_status = "resuming"
    session.add(ticket)
    session.commit()

    try:
        async_result = resume_ticket_approval.delay(
            ticket.id,
            department_id,
            decision.model_dump(),
        )
        task_id = async_result.id
    except Exception as exc:  # pragma: no cover - broker caído
        logger.exception("No se pudo encolar la decisión %s", ticket.id)
        ticket.approval_status = "pending"
        ticket.approval_error = f"No se pudo encolar la decisión: {exc}"[:2000]
        session.add(ticket)
        session.commit()
        raise HTTPException(
            status_code=503,
            detail="No se pudo encolar la decisión de aprobación.",
        ) from exc

    pending_remaining = sum(
        1
        for item in sections.values()
        if item.get("approval_status") == "pending_approval"
        and item.get("department_id") != department_id
    )
    return RfpApprovalResumeResponse(
        ticket_id=ticket.id,
        task_id=task_id,
        department_id=department_id,
        action=decision.action,
        status=ticket.status,
        pending_remaining=pending_remaining,
    )


@router.get(
    "/tickets/{ticket_id}/final-document",
    response_model=RfpFinalDocumentRead,
    summary="Documento final consolidado de las secciones aprobadas",
)
def get_rfp_final_document(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpFinalDocumentRead:
    return get_final_document(session, ticket_id)


@router.get(
    "/tickets/{ticket_id}/final-document/download",
    summary="Descargar el documento final en Markdown",
)
def download_rfp_final_document(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> Response:
    filename, markdown = get_final_document_markdown(session, ticket_id)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@router.get(
    "/tickets/{ticket_id}/trace",
    response_model=RfpTraceRead,
    summary="Trazabilidad de nodos, agentes, inputs, outputs y timestamps",
)
def get_rfp_trace(
    ticket_id: str,
    _=Depends(require_manager),
    session: Session = Depends(get_db),
) -> RfpTraceRead:
    return get_trace(session, ticket_id)
