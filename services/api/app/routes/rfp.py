"""Router HTTP de recepción de RFPs (extiende el backend existente)."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlmodel import Session

from database import get_db
from models import RFP_STATUS_ANALYZING, RFP_STATUS_ERROR, RfpTicket
from schemas import (
    RfpTicketListItem,
    RfpTicketRead,
    RfpTicketStatusRead,
    RfpUploadResponse,
)
from app.core.dependencies import require_manager
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
from app.tasks.rfp_intake import process_rfp_ticket

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rfp", tags=["rfp"])


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
