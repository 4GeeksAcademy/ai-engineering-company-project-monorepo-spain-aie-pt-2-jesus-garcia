"""Contrato del chat con memoria y de los endpoints de administración."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent.memory import config, service, store
from app.agent.memory.models import AgentMemoryEntry, AgentMemoryProposal
from app.agent.memory.scopes import normalize_scope
from app.agent.memory.schemas import MemoryProposalView
from app.agent.runner import AgentResult
from app.routes import agent_memory as agent_memory_route
from database import engine

SEUR_MESSAGE = (
    "En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que usar "
    "el carrier local desde el mes pasado."
)
CLIENT_MESSAGE = (
    "El cliente de cosméticos siempre quiere su reporte mensual con el "
    "desglose de devoluciones primero, antes que el volumen de envíos."
)


def _proposal(
    *,
    memory_type: str = "carrier_rule",
    scope: dict | None = None,
    fact: str = (
        "SEUR ya no cubre la zona rural de Zaragoza; usar el carrier local "
        "desde el mes pasado."
    ),
    quote: str = "SEUR ya no cubre esa zona rural de Zaragoza",
) -> dict:
    normalized = normalize_scope(
        scope
        or {"tipo": "carrier", "carrier": "SEUR", "pais": "ES", "zona": "rural"},
        memory_type,
    )
    return {
        "memory_type": memory_type,
        "scope": normalized.model_dump(),
        "fact": fact,
        "reason": "Corrección aportada por el usuario",
        "source_quote": quote,
    }


def _fake_run(calls: list[tuple[str, list[dict]]], proposal: dict | None):
    def run(question: str, **kwargs) -> AgentResult:
        calls.append((question, kwargs.get("memory_context") or []))
        if proposal and question.startswith(("En realidad", "El cliente")):
            return AgentResult(
                run_id="run-proposal",
                status="ok",
                answer="Entendido: SEUR ya no cubre esa zona rural.",
                error=None,
                trace_path="/tmp/run-proposal.json",
                memory_proposal=proposal,
                memory_used=False,
            )
        return AgentResult(
            run_id="run-answer",
            status="ok",
            answer=f"Respuesta a: {question}",
            error=None,
            trace_path="/tmp/run-answer.json",
            memory_proposal=None,
            memory_used=bool(kwargs.get("memory_context")),
        )

    return run


def _intent(payload: dict):
    def call(messages, **kwargs):
        return payload, "{}"

    return call


def test_approved_cycle_writes_memory_and_uses_it_later(monkeypatch):
    calls: list[tuple[str, list[dict]]] = []
    monkeypatch.setattr(service, "run_agent", _fake_run(calls, _proposal()))

    first = service.chat(
        SEUR_MESSAGE,
        user={"id": "u-memory", "role": "manager"},
        session_id="session-a",
    )
    assert first.memory is not None
    assert first.memory.pending_proposal is not None
    assert first.memory.pending_proposal.scope_label == "SEUR · ES · zona rural"
    assert first.answer.endswith(config.MEMORY_QUESTION)

    second = service.chat(
        "sí, guárdalo",
        user={"id": "u-memory", "role": "manager"},
        session_id="session-a",
        intent_llm=_intent(
            {"decision": "approve", "confianza": 0.95, "pregunta_restante": None}
        ),
    )
    assert second.memory is not None
    assert second.memory.resolution is not None
    assert second.memory.resolution.status == "approved"
    assert "recordaré" in second.answer.lower()

    third = service.chat(
        "¿Qué carrier usamos para la zona rural de Zaragoza?",
        user={"id": "u-memory", "role": "manager"},
        session_id="session-a",
    )
    assert third.answer.startswith("Respuesta a:")
    assert calls[-1][1], "La tercera interacción debía recibir memoria"
    assert "SEUR" in calls[-1][1][0]["fact"]


def test_rejected_cycle_leaves_memory_unchanged(monkeypatch):
    calls: list[tuple[str, list[dict]]] = []
    proposal = _proposal(
        memory_type="client_preference",
        scope={"tipo": "client", "cliente": "cosméticos"},
        fact=(
            "El cliente de cosméticos quiere el desglose de devoluciones "
            "primero en su reporte mensual."
        ),
        quote="siempre quiere su reporte mensual con el desglose de devoluciones primero",
    )
    monkeypatch.setattr(service, "run_agent", _fake_run(calls, proposal))

    first = service.chat(
        CLIENT_MESSAGE,
        user={"id": "u-reject", "role": "manager"},
        session_id="session-b",
    )
    assert first.memory.pending_proposal is not None

    second = service.chat(
        "no, eso era solo para esta campaña",
        user={"id": "u-reject", "role": "manager"},
        session_id="session-b",
        intent_llm=_intent(
            {"decision": "reject", "confianza": 0.92, "pregunta_restante": None}
        ),
    )
    assert second.memory.resolution.status == "rejected"
    assert "no guardaré" in second.answer.lower()

    third = service.chat(
        "¿Cómo quiere el reporte el cliente de cosméticos?",
        user={"id": "u-reject", "role": "manager"},
        session_id="session-b",
    )
    assert calls[-1][1] == []
    with Session(engine) as db:
        assert db.exec(select(AgentMemoryEntry)).all() == []


def test_unrelated_message_rejects_pending_by_default(monkeypatch):
    calls: list[tuple[str, list[dict]]] = []
    monkeypatch.setattr(service, "run_agent", _fake_run(calls, _proposal()))

    service.chat(
        SEUR_MESSAGE,
        user={"id": "u-unrelated", "role": "manager"},
        session_id="session-c",
    )
    second = service.chat(
        "¿Cuál es el SLA de un envío estándar?",
        user={"id": "u-unrelated", "role": "manager"},
        session_id="session-c",
        intent_llm=_intent(
            {"decision": "unrelated", "confianza": 0.9, "pregunta_restante": None}
        ),
    )
    assert second.memory.resolution.status == "rejected"
    assert second.answer.startswith("Respuesta a: ¿Cuál es el SLA")
    with Session(engine) as db:
        proposal = db.exec(select(AgentMemoryProposal)).one()
        assert proposal.status == "rejected"
        assert db.exec(select(AgentMemoryEntry)).all() == []


def test_edit_cycle_writes_the_edited_scope_and_fact(monkeypatch):
    calls: list[tuple[str, list[dict]]] = []
    monkeypatch.setattr(service, "run_agent", _fake_run(calls, _proposal()))
    service.chat(
        SEUR_MESSAGE,
        user={"id": "u-edit", "role": "manager"},
        session_id="session-d",
    )
    edited_scope = normalize_scope(
        {"tipo": "carrier", "carrier": "SEUR", "pais": "ES", "zona": "norte"},
        "carrier_rule",
    )
    second = service.chat(
        "guárdalo pero solo para la zona norte",
        user={"id": "u-edit", "role": "manager"},
        session_id="session-d",
        intent_llm=_intent(
            {
                "decision": "edit",
                "confianza": 0.9,
                "pregunta_restante": None,
                "propuesta_editada": {
                    "tipo": "carrier_rule",
                    "alcance": edited_scope.model_dump(),
                    "hecho": "SEUR ya no cubre la zona norte de Zaragoza.",
                    "motivo": "Ajuste del alcance",
                    "cita_origen": "solo para la zona norte",
                },
            }
        ),
    )
    assert second.memory.resolution.status == "edited"
    with Session(engine) as db:
        entry = db.exec(select(AgentMemoryEntry)).one()
        assert entry.scope_key == "carrier:SEUR:ES:norte"
        assert entry.fact == "SEUR ya no cubre la zona norte de Zaragoza."


def test_approval_and_follow_up_question_continue_in_the_same_turn(monkeypatch):
    calls: list[tuple[str, list[dict]]] = []
    monkeypatch.setattr(service, "run_agent", _fake_run(calls, _proposal()))
    service.chat(
        SEUR_MESSAGE,
        user={"id": "u-follow", "role": "manager"},
        session_id="session-e",
    )
    second = service.chat(
        "sí, guárdalo. ¿Y el SLA de un envío estándar?",
        user={"id": "u-follow", "role": "manager"},
        session_id="session-e",
        intent_llm=_intent(
            {
                "decision": "approve",
                "confianza": 0.95,
                "pregunta_restante": "¿Y el SLA de un envío estándar?",
            }
        ),
    )
    assert second.memory.resolution.status == "approved"
    assert calls[-1][0] == "¿Y el SLA de un envío estándar?"
    assert second.answer.startswith("Hecho. Lo recordaré")
    assert "Respuesta a: ¿Y el SLA" in second.answer


def test_pending_proposal_is_scoped_to_the_user(monkeypatch):
    calls: list[tuple[str, list[dict]]] = []
    monkeypatch.setattr(service, "run_agent", _fake_run(calls, _proposal()))
    service.chat(
        SEUR_MESSAGE,
        user={"id": "u-owner", "role": "manager"},
        session_id="session-f",
    )
    other = service.chat(
        "¿Cuál es el SLA de un envío?",
        user={"id": "u-other", "role": "manager"},
        session_id="session-g",
        intent_llm=_intent(
            {"decision": "approve", "confianza": 1.0, "pregunta_restante": None}
        ),
    )
    assert other.memory is None
    with Session(engine) as db:
        proposal = db.exec(select(AgentMemoryProposal)).one()
        assert proposal.user_id == "u-owner"
        assert proposal.status == "pending"


# --- HTTP -------------------------------------------------------------------


def test_agent_chat_requires_auth(client):
    response = client.post("/agent/chat", json={"message": "Hola"})
    assert response.status_code in (401, 403)


def test_agent_chat_returns_the_proposal_in_the_same_response(
    client, auth_headers, monkeypatch
):
    proposal = MemoryProposalView(
        id="p1",
        memory_type="carrier_rule",
        scope={"kind": "carrier"},
        scope_label="SEUR · ES · zona rural",
        fact="SEUR ya no cubre la zona rural de Zaragoza.",
        reason="Corrección",
        question=config.MEMORY_QUESTION,
        created_at="2026-11-14T10:00:00+00:00",
    )
    result = service.ChatResult(
        session_id="s1",
        run_id="r1",
        answer=f"Entendido.\n\n{config.MEMORY_QUESTION}",
        status="ok",
        memory=service.ChatMemory(pending_proposal=proposal),
    )
    monkeypatch.setattr(agent_memory_route, "chat", lambda *a, **k: result)

    response = client.post(
        "/agent/chat",
        json={"message": "SEUR ya no cubre la zona rural"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "s1"
    assert body["memory"]["pending_proposal"]["id"] == "p1"
    assert body["answer"].endswith(config.MEMORY_QUESTION)


def test_agent_chat_maps_invalid_question_and_errors(
    client, auth_headers, monkeypatch
):
    monkeypatch.setattr(
        agent_memory_route,
        "chat",
        lambda *a, **k: service.ChatResult(
            session_id="s1",
            run_id=None,
            answer="",
            status="invalid_question",
            error="La pregunta no puede estar vacía.",
        ),
    )
    invalid = client.post(
        "/agent/chat", json={"message": " "}, headers=auth_headers
    )
    assert invalid.status_code == 422

    monkeypatch.setattr(
        agent_memory_route,
        "chat",
        lambda *a, **k: service.ChatResult(
            session_id="s1",
            run_id=None,
            answer="",
            status="error",
            error="boom",
        ),
    )
    failed = client.post(
        "/agent/chat", json={"message": "Hola"}, headers=auth_headers
    )
    assert failed.status_code == 502
    assert "detail" in failed.json()


def test_memory_read_is_available_to_any_authenticated_user(
    client, auth_headers, user_headers
):
    assert client.get("/agent/memory", headers=auth_headers).status_code == 200
    assert client.get("/agent/memory", headers=user_headers).status_code == 200


def test_audit_and_consolidation_require_manager(
    client, auth_headers, user_headers
):
    assert (
        client.get("/agent/memory/proposals", headers=user_headers).status_code
        == 403
    )
    assert (
        client.post("/agent/memory/consolidate", headers=user_headers).status_code
        == 403
    )
    assert (
        client.get("/agent/memory/proposals", headers=auth_headers).status_code
        == 200
    )
    response = client.post("/agent/memory/consolidate", headers=auth_headers)
    assert response.status_code == 200
    assert "counts" in response.json()


def test_retire_unknown_entry_returns_404(client, auth_headers):
    response = client.post(
        "/agent/memory/no-existe/retire", headers=auth_headers
    )
    assert response.status_code == 404


def test_manager_decision_endpoint_requires_manager(client, auth_headers, user_headers):
    forbidden = client.post(
        "/agent/memory/proposals/no-existe/approve",
        json={"decision": "approve"},
        headers=user_headers,
    )
    assert forbidden.status_code == 403
    missing = client.post(
        "/agent/memory/proposals/no-existe/approve",
        json={"decision": "approve"},
        headers=auth_headers,
    )
    assert missing.status_code == 404
