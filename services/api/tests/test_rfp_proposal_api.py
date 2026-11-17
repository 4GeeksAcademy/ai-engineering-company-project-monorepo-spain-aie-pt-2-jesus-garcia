"""Tests del API de generación de propuestas (extiende el router RFP)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, delete, select

from app.services.rfp_proposal_service import SqlRfpProposalRepository
from app.services.rfp_service import create_ticket
from database import engine
from models import (
    RFP_HANDOFF_READY,
    RFP_STATUS_AWAITING_APPROVAL,
    RFP_STATUS_COMPLETE,
    RfpDepartmentSection,
    RfpMetadata,
    RfpSectionEvaluation,
    RfpTicket,
)

ROOT = Path(__file__).resolve().parents[3]
PIPELINES_DIR = ROOT / "tests" / "pipelines"
if str(PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINES_DIR))

from rfp_proposal_support import ScriptedProposalLlm, prose  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_rfp_tables():
    if engine is None:
        yield
        return
    for model in (
        RfpSectionEvaluation,
        RfpDepartmentSection,
        RfpMetadata,
        RfpTicket,
    ):
        model.__table__.create(engine, checkfirst=True)
    with Session(engine) as session:
        for model in (
            RfpSectionEvaluation,
            RfpDepartmentSection,
            RfpMetadata,
            RfpTicket,
        ):
            session.exec(delete(model))
        session.commit()
    yield


@pytest.fixture(autouse=True)
def _isolated_traces(tmp_path, monkeypatch):
    monkeypatch.setenv("RFP_PROPOSAL_TRACE_DIR", str(tmp_path / "traces"))
    yield


def _handoff(ticket_id: str) -> dict:
    return {
        "contract_version": "rfp-intake-v1",
        "ticket_id": ticket_id,
        "rfp_id": "RFP-TEST-P2",
        "status": "analisis_completo",
        "generated_at": "2026-11-15T10:00:00+00:00",
        "client": {
            "name": "ModaViva, S.L.",
            "country": "Spain",
            "currency": "EUR",
            "contact": {"name": "Elena Bosch"},
        },
        "currency": "EUR",
        "services_requested": ["warehousing"],
        "unknown_services": [],
        "rfp_facts": {
            "monthly_volume": None,
            "sku_count": 15_000,
            "return_volume": None,
            "return_rate": None,
            "deadline": "2026-08-28",
            "budget_range": None,
        },
        "departments": [
            {
                "department_id": "warehouse",
                "department_label": "Warehouse Operations",
                "responsible": "Ana Whitfield",
                "focus": "Capacidad para 15.000 SKUs",
                "key_aspects": [
                    {
                        "aspect": "Volumen de SKUs",
                        "detail": "La RFP declara 15.000 SKUs.",
                        "evidence": "15.000 SKUs",
                        "confidence": "high",
                    }
                ],
                "open_questions": [
                    "Falta el volumen mensual de pedidos: confirmarlo."
                ],
            }
        ],
        "questions_to_ask": [],
        "conflicts": [],
        "sales_summary": "- ModaViva (España, EUR) pide almacenamiento.",
        "next_steps": [],
        "source": {
            "pdf_path": "/does/not/exist.pdf",
            "markdown_path": "/does/not/exist.md",
            "document_metadata": {},
            "readability_metrics": {},
            "classification": {},
        },
    }


def _ready_ticket(session: Session) -> RfpTicket:
    ticket = create_ticket(
        session,
        filename="rfp.pdf",
        pdf_path=Path("/does/not/exist.pdf"),
        file_sha256="0" * 64,
    )
    ticket.status = RFP_STATUS_COMPLETE
    ticket.handoff_status = RFP_HANDOFF_READY
    ticket.handoff_payload = _handoff(ticket.id)
    ticket.handoff_at = datetime.now(timezone.utc)
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


def _patch_task(monkeypatch):
    from app.tasks import rfp_proposal as task_module

    calls: list[str] = []

    class FakeResult:
        id = "task-proposal-1"

    def fake_delay(ticket_id: str):
        calls.append(ticket_id)
        return FakeResult()

    monkeypatch.setattr(task_module.generate_proposal, "delay", fake_delay)
    return calls


def test_start_proposal_enqueues_ready_ticket(client, auth_headers, monkeypatch):
    calls = _patch_task(monkeypatch)
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket_id = ticket.id

    response = client.post(
        f"/rfp/tickets/{ticket_id}/proposal", headers=auth_headers
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["ticket_id"] == ticket_id
    assert payload["task_id"] == "task-proposal-1"
    assert calls == [ticket_id]

    with Session(engine) as session:
        ticket = session.get(RfpTicket, ticket_id)
        assert ticket.proposal_task_id == "task-proposal-1"
        assert ticket.proposal_stage == "encolado"


def test_start_proposal_rejects_ticket_without_handoff(client, auth_headers):
    with Session(engine) as session:
        ticket = create_ticket(
            session,
            filename="rfp.pdf",
            pdf_path=Path("/does/not/exist.pdf"),
            file_sha256="1" * 64,
        )
        ticket_id = ticket.id

    response = client.post(
        f"/rfp/tickets/{ticket_id}/proposal", headers=auth_headers
    )

    assert response.status_code == 409


def test_start_proposal_rejects_invalid_handoff(client, auth_headers):
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket.handoff_payload = {**_handoff(ticket.id), "contract_version": "v0"}
        session.add(ticket)
        session.commit()
        ticket_id = ticket.id

    response = client.post(
        f"/rfp/tickets/{ticket_id}/proposal", headers=auth_headers
    )

    assert response.status_code == 409
    assert "handoff" in response.json()["detail"].lower()


def test_start_proposal_rejects_concurrent_run(client, auth_headers):
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket.status = "generando_borrador"
        session.add(ticket)
        session.commit()
        ticket_id = ticket.id

    response = client.post(
        f"/rfp/tickets/{ticket_id}/proposal", headers=auth_headers
    )

    assert response.status_code == 409


def test_get_proposal_returns_404_before_generation(client, auth_headers):
    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket_id = ticket.id

    response = client.get(
        f"/rfp/tickets/{ticket_id}/proposal", headers=auth_headers
    )

    assert response.status_code == 404


def test_pipeline_persists_drafts_and_evaluations_in_postgres(
    client, auth_headers
):
    from data.pipelines.rfp_proposal import run_proposal_generation

    with Session(engine) as session:
        ticket = _ready_ticket(session)
        ticket_id = ticket.id

    llm = ScriptedProposalLlm(
        generators={"warehouse": prose(aspects=["Volumen de SKUs"])}
    )
    with Session(engine) as session:
        repo = SqlRfpProposalRepository(session)
        result = run_proposal_generation(ticket_id, repo, llm=llm)

    assert result["status"] == RFP_STATUS_AWAITING_APPROVAL

    with Session(engine) as session:
        ticket = session.get(RfpTicket, ticket_id)
        assert ticket.status == RFP_STATUS_AWAITING_APPROVAL
        assert ticket.proposal_payload["contract_version"] == "rfp-proposal-v1"

        section = session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id
            )
        ).first()
        assert section is not None
        assert section.draft_content
        assert section.draft_payload["pricing"]
        assert section.evaluation_results["overall_pass"] is True
        assert section.iteration_count == 1
        assert section.generation_status == "evaluated_pass"

        history = session.exec(
            select(RfpSectionEvaluation).where(
                RfpSectionEvaluation.ticket_id == ticket_id
            )
        ).all()
        assert len(history) == 1
        assert history[0].compliance["pass"] is True

    response = client.get(
        f"/rfp/tickets/{ticket_id}/proposal", headers=auth_headers
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == RFP_STATUS_AWAITING_APPROVAL
    assert payload["currency"] == "EUR"
    assert payload["sections"][0]["department_id"] == "warehouse"
    assert payload["sections"][0]["provisional"] is False
    assert payload["sections"][0]["evaluation_results"]["readability"]["pass"] is True
