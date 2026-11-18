"""Tests del API de aprobación humana y cierre (Parte 3)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, delete

from app.services.rfp_approval_service import (
    resume_department,
    start_approvals,
)
from app.services.rfp_service import create_ticket
from database import engine
from models import (
    RFP_HANDOFF_READY,
    RFP_STATUS_AWAITING_APPROVAL,
    RfpArbitration,
    RfpDepartmentSection,
    RfpFinalDocument,
    RfpMetadata,
    RfpNodeTrace,
    RfpSectionEvaluation,
    RfpTicket,
)
from schemas import RfpApprovalDecisionRequest

ROOT = Path(__file__).resolve().parents[3]
PIPELINES_DIR = ROOT / "tests" / "pipelines"
if str(PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINES_DIR))

from rfp_approval_support import proposal_for_modaviva  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_rfp_tables():
    if engine is None:
        yield
        return
    for model in (
        RfpNodeTrace,
        RfpArbitration,
        RfpFinalDocument,
        RfpSectionEvaluation,
        RfpDepartmentSection,
        RfpMetadata,
        RfpTicket,
    ):
        model.__table__.create(engine, checkfirst=True)
    with Session(engine) as session:
        for model in (
            RfpNodeTrace,
            RfpArbitration,
            RfpFinalDocument,
            RfpSectionEvaluation,
            RfpDepartmentSection,
            RfpMetadata,
            RfpTicket,
        ):
            session.exec(delete(model))
        session.commit()
    yield


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "RFP_APPROVAL_CHECKPOINT_DB", str(tmp_path / "checkpoints.db")
    )
    monkeypatch.setenv(
        "RFP_APPROVAL_TRACE_DIR", str(tmp_path / "approval-traces")
    )
    monkeypatch.setenv("RFP_TRACE_DIR", str(tmp_path / "intake-traces"))
    monkeypatch.setenv(
        "RFP_PROPOSAL_TRACE_DIR", str(tmp_path / "proposal-traces")
    )
    monkeypatch.setenv("RFP_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("RFP_APPROVAL_MAX_ROUNDS", "2")
    yield


def _ready_ticket(session: Session) -> RfpTicket:
    ticket = create_ticket(
        session,
        filename="modaviva.pdf",
        pdf_path=Path("/does/not/exist.pdf"),
        file_sha256="0" * 64,
    )
    proposal, intake = proposal_for_modaviva(ticket.id)
    ticket.status = RFP_STATUS_AWAITING_APPROVAL
    ticket.proposal_status = RFP_STATUS_AWAITING_APPROVAL
    ticket.handoff_status = RFP_HANDOFF_READY
    ticket.handoff_payload = intake
    ticket.handoff_at = datetime.now(timezone.utc)
    ticket.proposal_payload = proposal
    ticket.proposal_ready_at = datetime.now(timezone.utc)
    session.add(ticket)
    for section in proposal["sections"]:
        session.add(
            RfpDepartmentSection(
                ticket_id=ticket.id,
                department_id=section["department_id"],
                responsible=section["responsible"],
                draft_content=section["draft_content"],
                draft_payload=section["draft_payload"],
                evaluation_results=section["evaluation_results"],
                generation_status=section.get("status"),
                iteration_count=int(section.get("iteration_count") or 0),
                approval_status="pending_approval",
            )
        )
    session.commit()
    session.refresh(ticket)
    return ticket


def _patch_delay(monkeypatch):
    from app.routes import rfp as rfp_route

    calls: list[dict] = []

    class FakeResult:
        id = "task-approval-1"

    def fake_start_delay(ticket_id: str):
        calls.append({"kind": "start", "ticket_id": ticket_id})
        return FakeResult()

    def fake_resume_delay(ticket_id: str, department_id: str, decision: dict):
        calls.append(
            {
                "kind": "resume",
                "ticket_id": ticket_id,
                "department_id": department_id,
                "decision": decision,
            }
        )
        return FakeResult()

    monkeypatch.setattr(
        rfp_route.start_ticket_approvals, "delay", fake_start_delay
    )
    monkeypatch.setattr(
        rfp_route.resume_ticket_approval, "delay", fake_resume_delay
    )
    return calls


def test_start_enqueues_ready_ticket(client, auth_headers, monkeypatch):
    calls = _patch_delay(monkeypatch)
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket_id = ticket.id

    response = client.post(
        f"/rfp/tickets/{ticket_id}/approvals/start", headers=auth_headers
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["task_id"] == "task-approval-1"
    assert calls == [{"kind": "start", "ticket_id": ticket_id}]
    with Session(engine) as session:
        stored = session.get(RfpTicket, ticket_id)
        assert stored.approval_status == "encolado"
        assert stored.approval_task_id == "task-approval-1"


def test_start_rejects_ticket_without_proposal(client, auth_headers):
    with Session(engine) as session:
        ticket = create_ticket(
            session,
            filename="rfp.pdf",
            pdf_path=Path("/does/not/exist.pdf"),
            file_sha256="1" * 64,
        )
        ticket.status = RFP_STATUS_AWAITING_APPROVAL
        session.add(ticket)
        session.commit()
        ticket_id = ticket.id

    response = client.post(
        f"/rfp/tickets/{ticket_id}/approvals/start", headers=auth_headers
    )
    assert response.status_code == 409
    assert "propuesta" in response.json()["detail"].lower()


def test_start_and_resume_flow_generates_final_document(client, auth_headers):
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket_id = ticket.id
        summary = start_approvals(session, ticket_id)

    assert {item["department_id"] for item in summary["pending"]} == {
        "warehouse",
        "reverse",
    }
    response = client.get(
        f"/rfp/tickets/{ticket_id}/approvals", headers=auth_headers
    )
    assert response.status_code == 200
    approvals = response.json()
    assert approvals["status"] == "esperando_aprobación"
    assert len(approvals["pending"]) == 2
    pending = {item["department_id"]: item for item in approvals["pending"]}
    assert pending["warehouse"]["responsible"] == "Ana Whitfield"
    assert pending["warehouse"]["interrupt_id"]
    assert pending["warehouse"]["packet"]["section_markdown"]

    with Session(engine) as session:
        resume_department(
            session,
            ticket_id,
            "warehouse",
            RfpApprovalDecisionRequest(
                action="approve",
                approver="Ana Whitfield",
                comment="Capacidad validada.",
                interrupt_id=pending["warehouse"]["interrupt_id"],
            ),
        )

    response = client.get(
        f"/rfp/tickets/{ticket_id}/approvals", headers=auth_headers
    )
    approvals = response.json()
    assert approvals["status"] == "esperando_aprobación"
    assert [item["department_id"] for item in approvals["pending"]] == ["reverse"]
    assert approvals["decisions"][0]["approval_status"] == "approved"

    with Session(engine) as session:
        resume_department(
            session,
            ticket_id,
            "reverse",
            RfpApprovalDecisionRequest(
                action="approve",
                approver="Sofía Ramos",
                interrupt_id=pending["reverse"]["interrupt_id"],
            ),
        )

    response = client.get(
        f"/rfp/tickets/{ticket_id}/final-document", headers=auth_headers
    )
    assert response.status_code == 200
    document = response.json()
    assert document["currency"] == "EUR"
    assert "ModaViva" in document["markdown"]
    assert "Warehouse Operations" in document["markdown"]
    assert "Reverse Logistics" in document["markdown"]
    assert {item["approver"] for item in document["approved_by"]} == {
        "Ana Whitfield",
        "Sofía Ramos",
    }

    download = client.get(
        f"/rfp/tickets/{ticket_id}/final-document/download",
        headers=auth_headers,
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/markdown")
    assert "Propuesta comercial" in download.text

    detail = client.get(f"/rfp/tickets/{ticket_id}", headers=auth_headers)
    assert detail.json()["status"] == "terminado"
    assert detail.json()["final_document_ready"] is True


def test_resume_validates_approver_and_interrupt(client, auth_headers):
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket_id = ticket.id
        summary = start_approvals(session, ticket_id)
    pending = {item["department_id"]: item for item in summary["pending"]}

    wrong_approver = client.post(
        f"/rfp/tickets/{ticket_id}/approvals/warehouse",
        headers=auth_headers,
        json={
            "action": "approve",
            "approver": "Carlos Vega",
            "interrupt_id": pending["warehouse"]["interrupt_id"],
        },
    )
    assert wrong_approver.status_code == 422
    assert "Ana Whitfield" in wrong_approver.json()["detail"]

    missing_comment = client.post(
        f"/rfp/tickets/{ticket_id}/approvals/reverse",
        headers=auth_headers,
        json={
            "action": "reject",
            "approver": "Sofía Ramos",
            "interrupt_id": pending["reverse"]["interrupt_id"],
        },
    )
    assert missing_comment.status_code == 422
    assert "comentario" in missing_comment.json()["detail"].lower()

    stale_interrupt = client.post(
        f"/rfp/tickets/{ticket_id}/approvals/warehouse",
        headers=auth_headers,
        json={
            "action": "approve",
            "approver": "Ana Whitfield",
            "interrupt_id": "interrupt-obsoleto",
        },
    )
    assert stale_interrupt.status_code == 409
    assert "interrupt" in stale_interrupt.json()["detail"].lower()

    with Session(engine) as session:
        stored = session.get(RfpTicket, ticket_id)
        assert stored.status == RFP_STATUS_AWAITING_APPROVAL
        assert stored.approval_status in {None, "pending"}


def test_request_changes_keeps_section_pending(client, auth_headers, monkeypatch):
    _patch_delay(monkeypatch)
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket_id = ticket.id
        summary = start_approvals(session, ticket_id)
    pending = {item["department_id"]: item for item in summary["pending"]}

    response = client.post(
        f"/rfp/tickets/{ticket_id}/approvals/warehouse",
        headers=auth_headers,
        json={
            "action": "request_changes",
            "approver": "Ana Whitfield",
            "comment": "Confirma el volumen mensual antes de aprobar.",
            "interrupt_id": pending["warehouse"]["interrupt_id"],
        },
    )
    assert response.status_code == 202

    with Session(engine) as session:
        resume_department(
            session,
            ticket_id,
            "warehouse",
            RfpApprovalDecisionRequest(
                action="request_changes",
                approver="Ana Whitfield",
                comment="Confirma el volumen mensual antes de aprobar.",
                interrupt_id=pending["warehouse"]["interrupt_id"],
            ),
        )

    response = client.get(
        f"/rfp/tickets/{ticket_id}/approvals", headers=auth_headers
    )
    approvals = response.json()
    assert approvals["status"] == "esperando_aprobación"
    warehouse = next(
        item for item in approvals["pending"] if item["department_id"] == "warehouse"
    )
    assert warehouse["approval_round"] == 1
    assert warehouse["interrupt_id"] != pending["warehouse"]["interrupt_id"]
    assert "volumen" in warehouse["packet"]["section_markdown"].lower()


def test_trace_and_arbitration_endpoints(client, auth_headers):
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket_id = ticket.id
        summary = start_approvals(session, ticket_id)
    pending = {item["department_id"]: item for item in summary["pending"]}
    with Session(engine) as session:
        resume_department(
            session,
            ticket_id,
            "warehouse",
            RfpApprovalDecisionRequest(
                action="approve",
                approver="Ana Whitfield",
                interrupt_id=pending["warehouse"]["interrupt_id"],
            ),
        )

    response = client.get(
        f"/rfp/tickets/{ticket_id}/trace", headers=auth_headers
    )
    assert response.status_code == 200
    trace = response.json()
    part3 = [event for event in trace["events"] if event["part"] == 3]
    assert part3
    for event in part3:
        assert event["agent"]
        assert event["timestamp"]
        assert event["input"] is not None
        assert event["output"] is not None
    nodes = [event["node"] for event in part3]
    assert "prepare_approval" in nodes
    assert "await_approval" in nodes
    assert "record_approval" in nodes
    agents = {event["agent"] for event in part3}
    assert any(agent.startswith("human:") for agent in agents)


def test_approval_requires_manager_role(client, user_headers):
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket_id = ticket.id

    response = client.post(
        f"/rfp/tickets/{ticket_id}/approvals/start", headers=user_headers
    )
    assert response.status_code == 403
