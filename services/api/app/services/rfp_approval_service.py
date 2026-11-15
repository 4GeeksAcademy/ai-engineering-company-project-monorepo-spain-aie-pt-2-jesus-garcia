"""Servicio y repositorio SQL de la aprobación humana (Parte 3)."""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

# El worker Celery arranca desde ``services/api`` (local) o ``/app`` (Docker).
for _parent in Path(__file__).resolve().parents:
    if (_parent / "data" / "pipelines").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from fastapi import HTTPException
from sqlmodel import Session, select

from data.pipelines.rfp_intake.catalog import DEPARTMENTS, DEPARTMENT_ORDER
from data.pipelines.rfp_approval import (
    resume_approval,
    start_approval_flow,
)
from data.pipelines.rfp_approval.contracts import (
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    TICKET_AWAITING,
    TICKET_FINISHED,
    ApprovalError,
    normalize_proposal,
    proposal_sections,
)
from models import (
    RFP_STATUS_AWAITING_APPROVAL,
    RfpArbitration,
    RfpDepartmentSection,
    RfpFinalDocument,
    RfpNodeTrace,
    RfpTicket,
)
from schemas import (
    RfpApprovalDecisionRequest,
    RfpApprovalPacketRead,
    RfpApprovalsRead,
    RfpApprovalSummaryRead,
    RfpArbitrationRead,
    RfpFinalDocumentRead,
    RfpTraceEventRead,
    RfpTraceRead,
)
from app.services.rfp_proposal_service import SqlRfpProposalRepository
from app.services.rfp_service import raw_base_dir

logger = logging.getLogger(__name__)


def _synchronized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class SqlRfpApprovalRepository:
    """Implementación PostgreSQL/SQLite del puerto ``ApprovalRepository``."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._lock = threading.RLock()
        self._proposal = SqlRfpProposalRepository(session)

    # --- ticket / contexto -------------------------------------------------

    def _ticket(self, ticket_id: str) -> RfpTicket:
        ticket = self.session.get(RfpTicket, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        return ticket

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
            "proposal_payload": ticket.proposal_payload,
            "approval_status": ticket.approval_status,
            "approval_thread_id": ticket.approval_thread_id,
            "approval_run": ticket.approval_run or 0,
            "approval_task_id": ticket.approval_task_id,
            "approval_started_at": _iso(ticket.approval_started_at),
            "approval_completed_at": _iso(ticket.approval_completed_at),
            "approval_error": ticket.approval_error,
        }

    @_synchronized
    def get_proposal(self, ticket_id: str) -> dict | None:
        return self._ticket(ticket_id).proposal_payload

    @_synchronized
    def get_intake_handoff(self, ticket_id: str) -> dict | None:
        return self._ticket(ticket_id).handoff_payload

    @_synchronized
    def get_rfp_facts(self, ticket_id: str) -> dict:
        return self._proposal.get_rfp_facts(ticket_id)

    @_synchronized
    def get_sections(self, ticket_id: str) -> dict[str, dict]:
        ticket = self._ticket(ticket_id)
        proposal = normalize_proposal(ticket.proposal_payload, ticket_id=ticket_id)
        base_sections = proposal_sections(proposal)
        rows = list(
            self.session.exec(
                select(RfpDepartmentSection).where(
                    RfpDepartmentSection.ticket_id == ticket_id
                )
            ).all()
        )
        rows_by_department = {row.department_id: row for row in rows}
        sections: dict[str, dict] = {}
        for department_id, base in base_sections.items():
            row = rows_by_department.get(department_id)
            if row is None:
                sections[department_id] = {
                    **base,
                    "ticket_id": ticket_id,
                    "approval_status": base.get("approval_status")
                    or APPROVAL_PENDING,
                    "approval_round": 0,
                }
                continue
            sections[department_id] = {
                **base,
                "ticket_id": ticket_id,
                "department_id": department_id,
                "department_label": base.get("department_label")
                or DEPARTMENTS.get(department_id, {}).get("label"),
                "responsible": row.responsible
                or base.get("responsible")
                or DEPARTMENTS.get(department_id, {}).get("responsible"),
                "draft_content": row.draft_content
                if row.draft_content is not None
                else base.get("draft_content"),
                "draft_payload": row.draft_payload
                if row.draft_payload is not None
                else base.get("draft_payload") or {},
                "evaluation_results": row.evaluation_results
                if row.evaluation_results is not None
                else base.get("evaluation_results") or {},
                "generation_status": row.generation_status,
                "iteration_count": int(
                    row.iteration_count or base.get("iteration_count") or 0
                ),
                "approval_status": row.approval_status
                or base.get("approval_status")
                or APPROVAL_PENDING,
                "approver": row.approver,
                "approved_at": _iso(row.approved_at),
                "approval_comment": row.approval_comment,
                "approval_decided_at": _iso(row.approval_decided_at),
                "approval_round": int(row.approval_round or 0),
                "approval_interrupt_id": row.approval_interrupt_id,
                "approval_packet": row.approval_packet,
                "provisional": bool(row.needs_human_review)
                if row is not None
                else bool(base.get("provisional")),
                "review_reason": row.review_reason or base.get("review_reason"),
            }
        return sections

    @_synchronized
    def begin_approval_run(
        self, ticket_id: str, *, thread_id: str, run: int
    ) -> None:
        ticket = self._ticket(ticket_id)
        ticket.status = RFP_STATUS_AWAITING_APPROVAL
        ticket.proposal_status = RFP_STATUS_AWAITING_APPROVAL
        ticket.approval_status = "pending"
        ticket.approval_thread_id = thread_id
        ticket.approval_run = run
        ticket.approval_started_at = datetime.now(timezone.utc)
        ticket.approval_completed_at = None
        ticket.approval_error = None
        ticket.proposal_stage = TICKET_AWAITING
        ticket.error_message = None
        ticket.proposal_error = None
        rows = self.session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id
            )
        ).all()
        for row in rows:
            row.approval_status = APPROVAL_PENDING
            row.approver = None
            row.approved_at = None
            row.approval_comment = None
            row.approval_decided_at = None
            row.approval_round = 0
            row.approval_interrupt_id = None
            row.approval_packet = None
            row.updated_at = datetime.now(timezone.utc)
            self.session.add(row)
        ticket.updated_at = datetime.now(timezone.utc)
        self.session.add(ticket)
        self.session.commit()

    @_synchronized
    def set_approval_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        approval_status: str | None = None,
        stage: str | None = None,
        completed: bool = False,
    ) -> None:
        ticket = self._ticket(ticket_id)
        ticket.status = status
        ticket.proposal_status = status
        if approval_status is not None:
            ticket.approval_status = approval_status
        if stage:
            ticket.proposal_stage = stage
        if completed:
            ticket.approval_completed_at = datetime.now(timezone.utc)
        ticket.updated_at = datetime.now(timezone.utc)
        self.session.add(ticket)
        self.session.commit()

    # --- métodos que usa el subgrafo de la Parte 2 -------------------------

    def set_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        stage: str | None = None,
        force: bool = False,
    ) -> None:
        self._proposal.set_ticket_status(
            ticket_id, status, stage=stage, force=force
        )

    def save_draft(
        self,
        ticket_id: str,
        *,
        department_id: str,
        draft: dict,
        iteration: int,
    ) -> None:
        self._proposal.save_draft(
            ticket_id,
            department_id=department_id,
            draft=draft,
            iteration=iteration,
        )

    def save_evaluation(
        self,
        ticket_id: str,
        *,
        department_id: str,
        evaluation: dict,
    ) -> None:
        self._proposal.save_evaluation(
            ticket_id, department_id=department_id, evaluation=evaluation
        )

    def save_section_status(
        self,
        ticket_id: str,
        *,
        department_id: str,
        status: str,
        review_reason: str | None = None,
    ) -> None:
        self._proposal.save_section_status(
            ticket_id,
            department_id=department_id,
            status=status,
            review_reason=review_reason,
        )

    # --- aprobación --------------------------------------------------------

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
    def save_approval_packet(
        self,
        ticket_id: str,
        *,
        department_id: str,
        packet: dict,
        approval_round: int,
    ) -> None:
        row = self._section(ticket_id, department_id)
        row.approval_status = APPROVAL_PENDING
        row.approval_packet = packet
        row.approval_round = approval_round
        row.approval_interrupt_id = None
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()

    @_synchronized
    def save_approval_decision(
        self,
        ticket_id: str,
        *,
        department_id: str,
        status: str,
        approver: str | None,
        comment: str | None,
        decided_at: str | None,
        approval_round: int,
    ) -> None:
        row = self._section(ticket_id, department_id)
        row.approval_status = status
        row.approver = approver
        row.approval_comment = comment
        row.approval_decided_at = _parse_datetime(decided_at)
        row.approval_round = approval_round
        row.approval_interrupt_id = None
        row.approved_at = (
            _parse_datetime(decided_at) if status == APPROVAL_APPROVED else None
        )
        row.needs_human_review = status == APPROVAL_REJECTED
        if status == APPROVAL_REJECTED:
            row.review_reason = comment
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()

    @_synchronized
    def save_interrupt(
        self,
        ticket_id: str,
        *,
        department_id: str,
        interrupt_id: str,
        packet: dict,
    ) -> None:
        row = self._section(ticket_id, department_id)
        row.approval_status = APPROVAL_PENDING
        row.approval_interrupt_id = interrupt_id
        row.approval_packet = packet
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()

    @_synchronized
    def save_section_snapshot(self, ticket_id: str, *, section: dict) -> None:
        department_id = section.get("department_id")
        if not department_id:
            return
        row = self._section(ticket_id, department_id)
        if section.get("responsible"):
            row.responsible = section["responsible"]
        if section.get("draft_content") is not None:
            row.draft_content = section["draft_content"]
        if section.get("draft_payload") is not None:
            row.draft_payload = section["draft_payload"]
        if section.get("evaluation_results") is not None:
            row.evaluation_results = section["evaluation_results"]
        if section.get("generation_status") is not None:
            row.generation_status = section["generation_status"]
        if section.get("iteration_count") is not None:
            row.iteration_count = int(section["iteration_count"])
        if "needs_human_review" in section:
            row.needs_human_review = bool(section["needs_human_review"])
        if "review_reason" in section:
            row.review_reason = section["review_reason"]
        if section.get("approval_status"):
            row.approval_status = section["approval_status"]
        if "approver" in section:
            row.approver = section["approver"]
        if "approved_at" in section:
            row.approved_at = _parse_datetime(section["approved_at"])
        if "approval_comment" in section:
            row.approval_comment = section["approval_comment"]
        if section.get("approval_round") is not None:
            row.approval_round = int(section["approval_round"])
        if "approval_interrupt_id" in section:
            row.approval_interrupt_id = section["approval_interrupt_id"]
        if "approval_packet" in section:
            row.approval_packet = section["approval_packet"]
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()

    # --- traza / arbitraje / documento final -------------------------------

    @_synchronized
    def record_trace(
        self, ticket_id: str, events: list[dict], *, thread_id: str
    ) -> None:
        if not events:
            return
        rows = list(
            self.session.exec(
                select(RfpNodeTrace).where(RfpNodeTrace.ticket_id == ticket_id)
            ).all()
        )
        seen = {row.event_id for row in rows}
        sequence = max((row.sequence for row in rows), default=0)
        for event in events:
            event_id = event.get("event_id")
            if not event_id or event_id in seen:
                continue
            sequence += 1
            occurred_at = _parse_datetime(event.get("timestamp")) or datetime.now(
                timezone.utc
            )
            row = RfpNodeTrace(
                ticket_id=ticket_id,
                event_id=event_id,
                thread_id=(
                    event.get("thread_id")
                    or thread_id
                    or f"rfp-{ticket_id}"
                ),
                part=int(event.get("part") or 3),
                sequence=sequence,
                node=str(event.get("node") or "unknown")[:80],
                agent=(str(event["agent"])[:120] if event.get("agent") else None),
                department_id=(
                    str(event["department_id"])[:20]
                    if event.get("department_id")
                    else None
                ),
                input=event.get("input") or {},
                output=event.get("output") or {},
                occurred_at=occurred_at,
                duration_ms=(
                    int(event["duration_ms"])
                    if event.get("duration_ms") is not None
                    else None
                ),
            )
            self.session.add(row)
            seen.add(event_id)
        self.session.commit()

    @_synchronized
    def record_arbitration(
        self,
        ticket_id: str,
        *,
        round: int,
        conflict: dict,
        resolution: dict,
    ) -> None:
        row = RfpArbitration(
            ticket_id=ticket_id,
            round=round,
            trigger_id=str(conflict.get("trigger_id") or "unknown")[:40],
            arbitrator=(
                str(conflict["arbitrator"])[:120]
                if conflict.get("arbitrator")
                else None
            ),
            rule=conflict.get("rule"),
            affected_sections=list(conflict.get("affected_sections") or []),
            resolution=resolution,
            resolved=bool(resolution.get("resolved")),
        )
        self.session.add(row)
        self.session.commit()

    @_synchronized
    def save_final_document(
        self,
        ticket_id: str,
        *,
        document: dict,
        path: str | None = None,
    ) -> str | None:
        row = self.session.exec(
            select(RfpFinalDocument).where(
                RfpFinalDocument.ticket_id == ticket_id
            )
        ).first()
        if row is None:
            row = RfpFinalDocument(ticket_id=ticket_id)
        row.contract_version = document.get("contract_version") or "rfp-final-v1"
        row.currency = document.get("currency")
        row.sections = list(document.get("sections") or [])
        row.approved_by = list(document.get("approved_by") or [])
        row.markdown = document.get("markdown") or ""
        row.generated_at = _parse_datetime(document.get("generated_at")) or datetime.now(
            timezone.utc
        )
        target = path
        if not target:
            directory = raw_base_dir() / ticket_id
            directory.mkdir(parents=True, exist_ok=True)
            file_path = directory / "propuesta-final.md"
            try:
                file_path.write_text(row.markdown, encoding="utf-8")
                target = str(file_path)
            except OSError as exc:  # pragma: no cover
                logger.warning("No se pudo escribir el documento final: %s", exc)
        row.document_path = target
        self.session.add(row)
        self.session.commit()
        return target

    @_synchronized
    def get_final_document(self, ticket_id: str) -> dict | None:
        row = self.session.exec(
            select(RfpFinalDocument).where(
                RfpFinalDocument.ticket_id == ticket_id
            )
        ).first()
        if row is None:
            return None
        return {
            "contract_version": row.contract_version,
            "ticket_id": row.ticket_id,
            "currency": row.currency,
            "sections": row.sections,
            "approved_by": row.approved_by,
            "markdown": row.markdown,
            "document_path": row.document_path,
            "generated_at": _iso(row.generated_at),
        }

    @_synchronized
    def get_traces(self, ticket_id: str) -> list[dict]:
        rows = list(
            self.session.exec(
                select(RfpNodeTrace)
                .where(RfpNodeTrace.ticket_id == ticket_id)
                .order_by(RfpNodeTrace.sequence)
            ).all()
        )
        return [
            {
                "event_id": row.event_id,
                "part": row.part,
                "sequence": row.sequence,
                "node": row.node,
                "agent": row.agent,
                "department_id": row.department_id,
                "thread_id": row.thread_id,
                "input": row.input,
                "output": row.output,
                "timestamp": _iso(row.occurred_at),
                "duration_ms": row.duration_ms,
            }
            for row in rows
        ]

    @_synchronized
    def get_arbitrations(self, ticket_id: str) -> list[dict]:
        rows = list(
            self.session.exec(
                select(RfpArbitration)
                .where(RfpArbitration.ticket_id == ticket_id)
                .order_by(RfpArbitration.round, RfpArbitration.id)
            ).all()
        )
        return [
            {
                "round": row.round,
                "trigger_id": row.trigger_id,
                "arbitrator": row.arbitrator,
                "rule": row.rule,
                "affected_sections": row.affected_sections,
                "resolution": row.resolution,
                "resolved": row.resolved,
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ]

    @_synchronized
    def fail(self, ticket_id: str, *, stage: str, error: str) -> None:
        ticket = self._ticket(ticket_id)
        ticket.approval_error = error[:2000]
        ticket.approval_status = "error"
        ticket.updated_at = datetime.now(timezone.utc)
        self.session.add(ticket)
        self.session.commit()


# --- funciones de servicio --------------------------------------------------


def _packet_read(section: dict) -> RfpApprovalPacketRead:
    return RfpApprovalPacketRead(
        department_id=section.get("department_id"),
        department_label=section.get("department_label"),
        responsible=section.get("responsible"),
        approval_status=section.get("approval_status"),
        approval_round=int(section.get("approval_round") or 0),
        interrupt_id=section.get("approval_interrupt_id"),
        provisional=bool(section.get("provisional")),
        packet=section.get("approval_packet") or {},
    )


def get_approvals(session: Session, ticket_id: str) -> RfpApprovalsRead:
    repo = SqlRfpApprovalRepository(session)
    ticket = repo.get_ticket(ticket_id)
    if not ticket.get("proposal_payload"):
        return RfpApprovalsRead(
            ticket_id=ticket_id,
            rfp_id=ticket.get("rfp_id"),
            status=ticket.get("status"),
            approval_status=ticket.get("approval_status"),
            thread_id=ticket.get("approval_thread_id"),
            run=int(ticket.get("approval_run") or 0),
            max_rounds=_max_rounds(),
            pending=[],
            decisions=[],
            final_document_ready=ticket.get("status") == TICKET_FINISHED,
        )
    sections = repo.get_sections(ticket_id)
    pending = [
        _packet_read(section)
        for section in sections.values()
        if section.get("approval_status") == APPROVAL_PENDING
    ]
    decisions = [
        RfpApprovalSummaryRead(
            department_id=section.get("department_id"),
            department_label=section.get("department_label"),
            responsible=section.get("responsible"),
            approval_status=section.get("approval_status"),
            approver=section.get("approver"),
            approved_at=section.get("approved_at"),
            comment=section.get("approval_comment"),
            provisional=bool(section.get("provisional")),
            approval_round=int(section.get("approval_round") or 0),
        )
        for section in sections.values()
        if section.get("approval_status") in {APPROVAL_APPROVED, APPROVAL_REJECTED}
    ]
    return RfpApprovalsRead(
        ticket_id=ticket_id,
        rfp_id=ticket.get("rfp_id"),
        status=ticket.get("status"),
        approval_status=ticket.get("approval_status"),
        thread_id=ticket.get("approval_thread_id"),
        run=int(ticket.get("approval_run") or 0),
        max_rounds=_max_rounds(),
        pending=pending,
        decisions=decisions,
        final_document_ready=ticket.get("status") == TICKET_FINISHED,
    )


def _max_rounds() -> int:
    import os

    try:
        return max(1, int(os.getenv("RFP_APPROVAL_MAX_ROUNDS", "2")))
    except ValueError:
        return 2


def start_approvals(session: Session, ticket_id: str, *, llm=None) -> dict:
    repo = SqlRfpApprovalRepository(session)
    try:
        return start_approval_flow(ticket_id, repo, llm=llm)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def resume_department(
    session: Session,
    ticket_id: str,
    department_id: str,
    decision: RfpApprovalDecisionRequest,
    *,
    llm=None,
) -> dict:
    repo = SqlRfpApprovalRepository(session)
    payload = decision.model_dump()
    try:
        return resume_approval(ticket_id, department_id, payload, repo, llm=llm)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def get_final_document(session: Session, ticket_id: str) -> RfpFinalDocumentRead:
    repo = SqlRfpApprovalRepository(session)
    document = repo.get_final_document(ticket_id)
    if document is None:
        raise HTTPException(
            status_code=404,
            detail="El documento final todavía no está disponible.",
        )
    return RfpFinalDocumentRead(**document)


def get_final_document_markdown(session: Session, ticket_id: str) -> tuple[str, str]:
    document = get_final_document(session, ticket_id)
    filename = f"{ticket_id}-propuesta-final.md"
    return filename, document.markdown


def _read_trace_file(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _trace_path(directory_env: str, default_dir: Path, ticket_id: str) -> Path:
    import os

    configured = os.getenv(directory_env)
    directory = Path(configured) if configured else default_dir
    return directory / f"{ticket_id}.json"


def _part12_events(ticket_id: str, part: int, path: Path) -> list[dict]:
    payload = _read_trace_file(path)
    if not payload:
        return []
    state = payload.get("state") or {}
    raw_events = state.get("events") or []
    if not raw_events:
        return []
    started = payload.get("started_at")
    fallback = started or payload.get("finished_at")
    events: list[dict] = []
    for index, event in enumerate(raw_events, start=1):
        if not isinstance(event, dict):
            continue
        node = str(event.get("stage") or event.get("node") or "event")
        agent = event.get("agent")
        if not agent:
            if part == 1:
                agent = {
                    "validate_input": "orchestrator",
                    "convert_pdf": "converter",
                    "classify": "classifier",
                    "extract_metadata": "metadata_extractor",
                    "orchestrate": "orchestrator",
                    "worker": f"worker:{event.get('department_id') or 'departamento'}",
                    "synthesize": "synthesizer",
                }.get(node, "orchestrator")
            else:
                agent = {
                    "load_handoff": "proposal_orchestrator",
                    "department": f"generator:{event.get('department_id') or 'departamento'}",
                    "generate": f"generator:{event.get('department_id') or 'departamento'}",
                    "collect": f"evaluator:{event.get('department_id') or 'departamento'}",
                    "exhausted": f"evaluator:{event.get('department_id') or 'departamento'}",
                    "finalize_proposal": "proposal_orchestrator",
                }.get(node, "proposal_orchestrator")
        events.append(
            {
                "event_id": f"{part}-{ticket_id}-{index}",
                "part": part,
                "sequence": index,
                "node": node,
                "agent": agent,
                "department_id": event.get("department_id"),
                "thread_id": f"rfp-{ticket_id}:part-{part}",
                "input": {},
                "output": {
                    key: value
                    for key, value in event.items()
                    if key not in {"stage", "node", "agent", "timestamp"}
                },
                "timestamp": event.get("timestamp") or fallback,
                "duration_ms": None,
            }
        )
    return events


def get_trace(session: Session, ticket_id: str) -> RfpTraceRead:
    import os

    from app.services.rfp_service import repo_root

    repo = SqlRfpApprovalRepository(session)
    part1_default = repo_root() / "data" / "eval" / "rfp-traces"
    part2_default = repo_root() / "data" / "eval" / "rfp-proposal-traces"
    events: list[dict] = []
    events.extend(
        _part12_events(
            ticket_id, 1, _trace_path("RFP_TRACE_DIR", part1_default, ticket_id)
        )
    )
    events.extend(
        _part12_events(
            ticket_id,
            2,
            _trace_path("RFP_PROPOSAL_TRACE_DIR", part2_default, ticket_id),
        )
    )
    events.extend(repo.get_traces(ticket_id))
    events.sort(
        key=lambda item: (
            int(item.get("part") or 0),
            int(item.get("sequence") or 0),
        )
    )
    return RfpTraceRead(
        ticket_id=ticket_id,
        events=[RfpTraceEventRead(**event) for event in events],
        arbitrations=[
            RfpArbitrationRead(**item) for item in repo.get_arbitrations(ticket_id)
        ],
    )


__all__ = [
    "SqlRfpApprovalRepository",
    "get_approvals",
    "get_final_document",
    "get_final_document_markdown",
    "get_trace",
    "resume_department",
    "start_approvals",
]
