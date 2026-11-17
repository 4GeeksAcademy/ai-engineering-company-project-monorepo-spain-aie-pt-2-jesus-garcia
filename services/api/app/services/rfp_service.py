"""Servicio y repositorio SQL de la recepción de RFPs."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import threading
from functools import wraps
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

# El worker Celery puede arrancar desde ``services/api`` (local) o ``/app``
# (Docker). El paquete ``data`` vive en la raíz del monorepo; en Docker está
# montado como ``/app/data``. Se añade esa raíz antes de importar el pipeline.
for _parent in Path(__file__).resolve().parents:
    if (_parent / "data" / "pipelines").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from fastapi import HTTPException
from sqlmodel import Session, select

from app.realtime.events import publish_rfp_ticket_metadata_ready

from data.pipelines.rfp_intake.catalog import DEPARTMENT_ORDER
from data.pipelines.rfp_intake.repository import TicketNotFoundError
from models import (
    RFP_HANDOFF_NONE,
    RFP_HANDOFF_READY,
    RFP_STATUS_ANALYZING,
    RFP_STATUS_COMPLETE,
    RFP_STATUS_DISCARDED,
    RFP_STATUS_ERROR,
    RfpDepartmentSection,
    RfpMetadata,
    RfpTicket,
)
from schemas import (
    RfpDepartmentSectionRead,
    RfpMetadataRead,
    RfpTicketListItem,
    RfpTicketRead,
    RfpTicketStatusRead,
)

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = int(os.getenv("RFP_MAX_UPLOAD_MB", "20")) * 1024 * 1024
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class RfpUploadError(ValueError):
    """El archivo recibido no es un PDF aceptable."""


def repo_root() -> Path:
    configured = os.getenv("RFP_REPO_ROOT")
    if configured:
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "pipelines").is_dir():
            return parent
    return Path.cwd()


def raw_base_dir() -> Path:
    configured = os.getenv("RFP_RAW_DIR")
    if configured:
        return Path(configured)
    return repo_root() / "data" / "raw" / "rfp"


def sanitize_filename(name: str | None) -> str:
    candidate = Path(name or "rfp.pdf").name
    candidate = _SAFE_NAME_RE.sub("_", candidate).strip("._")
    if not candidate:
        candidate = "rfp.pdf"
    if not candidate.lower().endswith(".pdf"):
        candidate = f"{candidate}.pdf"
    return candidate[:120]


def store_pdf_bytes(
    ticket_id: str,
    filename: str | None,
    content: bytes,
) -> tuple[Path, str, str]:
    """Valida y guarda el PDF en ``data/raw/rfp/{ticket_id}/``."""

    if not content:
        raise RfpUploadError("El archivo está vacío.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise RfpUploadError(
            f"El PDF supera el límite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
    if not content.startswith(b"%PDF-"):
        raise RfpUploadError("El archivo no es un PDF válido (falta la cabecera %PDF-).")
    safe_name = sanitize_filename(filename)
    target_dir = raw_base_dir() / ticket_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    target.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    return target, safe_name, digest


def new_rfp_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"RFP-{stamp}-{uuid4().hex[:6].upper()}"


def create_ticket(
    session: Session,
    *,
    filename: str,
    pdf_path: Path,
    file_sha256: str,
) -> RfpTicket:
    ticket = RfpTicket(
        rfp_id=new_rfp_id(),
        status=RFP_STATUS_ANALYZING,
        pipeline_stage="recibido",
        raw_pdf_path=str(pdf_path),
        original_filename=filename,
        file_sha256=file_sha256,
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


def _metadata_by_ticket(
    session: Session, ticket_ids: Iterable[str]
) -> dict[str, RfpMetadata]:
    ids = list(ticket_ids)
    if not ids:
        return {}
    rows = session.exec(
        select(RfpMetadata).where(RfpMetadata.ticket_id.in_(ids))
    ).all()
    return {row.ticket_id: row for row in rows}


def _to_list_item(
    ticket: RfpTicket, metadata: RfpMetadata | None
) -> RfpTicketListItem:
    return RfpTicketListItem(
        ticket_id=ticket.id,
        rfp_id=ticket.rfp_id,
        status=ticket.status,
        pipeline_stage=ticket.pipeline_stage,
        original_filename=ticket.original_filename,
        client_name=metadata.client_name if metadata else None,
        client_country=metadata.client_country if metadata else None,
        currency=metadata.currency if metadata else None,
        discard_reason=ticket.discard_reason,
        error_message=ticket.error_message,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def list_tickets(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[RfpTicketListItem]:
    statement = select(RfpTicket).order_by(RfpTicket.created_at.desc())
    if status:
        statement = statement.where(RfpTicket.status == status)
    statement = statement.offset(max(0, offset)).limit(max(1, min(limit, 200)))
    tickets = list(session.exec(statement).all())
    metadata = _metadata_by_ticket(session, [ticket.id for ticket in tickets])
    return [_to_list_item(ticket, metadata.get(ticket.id)) for ticket in tickets]


def get_ticket(session: Session, ticket_id: str) -> RfpTicket:
    ticket = session.get(RfpTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")
    return ticket


def _metadata_read(metadata: RfpMetadata | None) -> RfpMetadataRead | None:
    if metadata is None:
        return None
    extraction = metadata.extraction or {}
    return RfpMetadataRead(
        client_name=metadata.client_name,
        client_country=metadata.client_country,
        currency=metadata.currency,
        language=metadata.language,
        services_requested=list(metadata.services_requested or []),
        departments_needed=list(metadata.departments_needed or []),
        monthly_volume=metadata.monthly_volume,
        deadline=metadata.deadline.isoformat() if metadata.deadline else None,
        budget_range=metadata.budget_range,
        contact=extraction.get("contact") or {},
        scope_notes=extraction.get("scope_notes") or [],
        unknown_services=extraction.get("unknown_services") or [],
        missing_fields=extraction.get("missing_fields") or [],
        readability_metrics=metadata.readability_metrics or {},
        document_metadata=metadata.document_metadata or {},
    )


def _section_read(section: RfpDepartmentSection) -> RfpDepartmentSectionRead:
    return RfpDepartmentSectionRead(
        department_id=section.department_id,
        responsible=section.responsible,
        key_aspects=list(section.key_aspects or []),
        open_questions=list(section.open_questions or []),
        assumed_facts=dict(section.assumed_facts or {}),
        unsupported_claims=list(section.unsupported_claims or []),
        approval_status=section.approval_status,
        approver=section.approver,
        draft_content=section.draft_content,
        draft_payload=section.draft_payload,
        evaluation_results=section.evaluation_results,
        generation_status=section.generation_status,
        iteration_count=section.iteration_count or 0,
        needs_human_review=bool(section.needs_human_review),
        review_reason=section.review_reason,
    )


def get_ticket_detail(session: Session, ticket_id: str) -> RfpTicketRead:
    ticket = get_ticket(session, ticket_id)
    metadata = session.exec(
        select(RfpMetadata).where(RfpMetadata.ticket_id == ticket.id)
    ).first()
    sections = list(
        session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket.id
            )
        ).all()
    )
    ordered = sorted(
        sections,
        key=lambda section: (
            DEPARTMENT_ORDER.index(section.department_id)
            if section.department_id in DEPARTMENT_ORDER
            else len(DEPARTMENT_ORDER)
        ),
    )
    return RfpTicketRead(
        ticket_id=ticket.id,
        rfp_id=ticket.rfp_id,
        status=ticket.status,
        pipeline_stage=ticket.pipeline_stage,
        original_filename=ticket.original_filename,
        raw_pdf_path=ticket.raw_pdf_path,
        markdown_path=ticket.markdown_path,
        file_sha256=ticket.file_sha256,
        classification=ticket.classification,
        discard_reason=ticket.discard_reason,
        error_message=ticket.error_message,
        handoff_status=ticket.handoff_status,
        handoff=ticket.handoff_payload,
        proposal_status=ticket.proposal_status,
        proposal_error=ticket.proposal_error,
        approval_status=ticket.approval_status,
        approval_thread_id=ticket.approval_thread_id,
        approval_error=ticket.approval_error,
        final_document_ready=ticket.status == "terminado",
        metadata=_metadata_read(metadata),
        sections=[_section_read(section) for section in ordered],
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def get_ticket_status(session: Session, ticket_id: str) -> RfpTicketStatusRead:
    ticket = get_ticket(session, ticket_id)
    return RfpTicketStatusRead(
        ticket_id=ticket.id,
        rfp_id=ticket.rfp_id,
        status=ticket.status,
        pipeline_stage=ticket.pipeline_stage,
        proposal_status=ticket.proposal_status,
        approval_status=ticket.approval_status,
        discard_reason=ticket.discard_reason,
        error_message=ticket.error_message,
        handoff_status=ticket.handoff_status,
        updated_at=ticket.updated_at,
    )


def _synchronized(method):
    """Serializa el acceso a la sesión: LangGraph lanza workers en paralelo."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class SqlRfpRepository:
    """Implementación PostgreSQL/SQLite del puerto del pipeline."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._lock = threading.RLock()

    def _get(self, ticket_id: str) -> RfpTicket:
        ticket = self.session.get(RfpTicket, ticket_id)
        if ticket is None:
            raise TicketNotFoundError(f"Ticket {ticket_id} no encontrado.")
        return ticket

    def _touch(self, ticket: RfpTicket) -> None:
        ticket.updated_at = datetime.now(timezone.utc)

    @_synchronized
    def get_ticket(self, ticket_id: str) -> dict:
        ticket = self._get(ticket_id)
        return {
            "ticket_id": ticket.id,
            "rfp_id": ticket.rfp_id,
            "status": ticket.status,
            "raw_pdf_path": ticket.raw_pdf_path,
            "markdown_path": ticket.markdown_path,
            "pipeline_stage": ticket.pipeline_stage,
        }

    @_synchronized
    def mark_processing(self, ticket_id: str) -> None:
        ticket = self._get(ticket_id)
        ticket.status = RFP_STATUS_ANALYZING
        ticket.pipeline_stage = "iniciado"
        ticket.error_message = None
        ticket.discard_reason = None
        ticket.classification = None
        ticket.handoff_status = RFP_HANDOFF_NONE
        ticket.handoff_payload = None
        ticket.handoff_at = None
        self._touch(ticket)
        self.session.add(ticket)
        self.session.commit()

    @_synchronized
    def set_stage(self, ticket_id: str, stage: str) -> None:
        ticket = self._get(ticket_id)
        ticket.pipeline_stage = stage
        self._touch(ticket)
        self.session.add(ticket)
        self.session.commit()

    @_synchronized
    def _metadata(self, ticket_id: str) -> RfpMetadata:
        metadata = self.session.exec(
            select(RfpMetadata).where(RfpMetadata.ticket_id == ticket_id)
        ).first()
        if metadata is None:
            metadata = RfpMetadata(ticket_id=ticket_id)
            self.session.add(metadata)
            self.session.commit()
            self.session.refresh(metadata)
        return metadata

    @_synchronized
    def save_conversion(
        self,
        ticket_id: str,
        *,
        markdown_path: str,
        document_metadata: dict,
        readability: dict,
    ) -> None:
        ticket = self._get(ticket_id)
        ticket.markdown_path = markdown_path
        self._touch(ticket)
        metadata = self._metadata(ticket_id)
        metadata.document_metadata = document_metadata or {}
        metadata.readability_metrics = readability or {}
        metadata.updated_at = datetime.now(timezone.utc)
        self.session.add(ticket)
        self.session.add(metadata)
        self.session.commit()

    @_synchronized
    def save_metadata(
        self,
        ticket_id: str,
        *,
        metadata: dict,
        classification: dict,
    ) -> None:
        ticket = self._get(ticket_id)
        is_first_metadata = ticket.classification is None
        row = self._metadata(ticket_id)
        row.client_name = metadata.get("client_name")
        row.client_country = metadata.get("client_country")
        row.currency = metadata.get("currency")
        row.language = metadata.get("language")
        row.services_requested = list(metadata.get("services_requested") or [])
        row.departments_needed = list(metadata.get("departments_needed") or [])
        row.monthly_volume = metadata.get("monthly_volume")
        deadline = metadata.get("deadline")
        if isinstance(deadline, str) and deadline:
            try:
                row.deadline = date.fromisoformat(deadline)
            except ValueError:
                row.deadline = None
        else:
            row.deadline = None
        row.budget_range = metadata.get("budget_range")
        row.extraction = {
            "unknown_services": metadata.get("unknown_services") or [],
            "missing_fields": metadata.get("missing_fields") or [],
            "contact": metadata.get("contact") or {},
            "scope_notes": metadata.get("scope_notes") or [],
            "evidence": metadata.get("evidence") or [],
            "sku_count": metadata.get("sku_count"),
            "return_volume": metadata.get("return_volume"),
            "return_rate": metadata.get("return_rate"),
        }
        row.updated_at = datetime.now(timezone.utc)
        ticket.classification = classification
        self._touch(ticket)
        self.session.add(row)
        self.session.add(ticket)
        self.session.commit()
        if is_first_metadata:
            # El pipeline confirmó que el documento es una RFP válida y ya
            # conoce cliente/país/servicios: se enriquece la notificación que
            # se emitió al registrar el ticket (mismo ticket_id, sin duplicar).
            publish_rfp_ticket_metadata_ready(ticket, row)

    @_synchronized
    def save_plan(self, ticket_id: str, *, departments: list[str]) -> None:
        row = self._metadata(ticket_id)
        row.departments_needed = list(departments)
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()

    @_synchronized
    def save_section(self, ticket_id: str, *, section: dict) -> None:
        department_id = section["department_id"]
        row = self.session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id,
                RfpDepartmentSection.department_id == department_id,
            )
        ).first()
        if row is None:
            row = RfpDepartmentSection(
                ticket_id=ticket_id, department_id=department_id
            )
        row.responsible = section.get("responsible")
        row.key_aspects = section.get("key_aspects") or []
        row.open_questions = section.get("open_questions") or []
        row.assumed_facts = section.get("assumed_facts") or {}
        row.unsupported_claims = section.get("unsupported_claims") or []
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()

    @_synchronized
    def discard(
        self,
        ticket_id: str,
        *,
        reason: str,
        classification: dict,
        stage: str = "descartado",
    ) -> None:
        ticket = self._get(ticket_id)
        ticket.status = RFP_STATUS_DISCARDED
        ticket.pipeline_stage = stage
        ticket.discard_reason = reason[:2000]
        ticket.classification = classification
        ticket.handoff_status = RFP_HANDOFF_NONE
        self._touch(ticket)
        self.session.add(ticket)
        self.session.commit()

    @_synchronized
    def complete(
        self,
        ticket_id: str,
        *,
        handoff: dict,
        stage: str = "completado",
    ) -> None:
        ticket = self._get(ticket_id)
        ticket.status = RFP_STATUS_COMPLETE
        ticket.pipeline_stage = stage
        ticket.handoff_status = RFP_HANDOFF_READY
        ticket.handoff_payload = handoff
        ticket.handoff_at = datetime.now(timezone.utc)
        ticket.error_message = None
        self._touch(ticket)
        self.session.add(ticket)
        self.session.commit()

    @_synchronized
    def fail(self, ticket_id: str, *, stage: str, error: str) -> None:
        ticket = self._get(ticket_id)
        ticket.status = RFP_STATUS_ERROR
        ticket.pipeline_stage = stage[:60]
        ticket.error_message = error[:2000]
        self._touch(ticket)
        self.session.add(ticket)
        self.session.commit()
