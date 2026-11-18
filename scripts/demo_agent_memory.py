"""Evidencia reproducible de los ciclos de memoria del agente.

Modo por defecto (``--offline``): usa ``TestClient``, un SQLite temporal y
dobles deterministas del LLM. No necesita red, Qdrant, MCP ni credenciales.
Ejecuta los ciclos aprobado, rechazado y bloqueado e imprime el JSON completo
(propuesta, decisión, entradas y auditoría) para pegarlo en la documentación.

Uso (desde ``services/api``):

    python -m scripts.demo_agent_memory

El script no toca la base de datos real ni las colecciones RAG.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="trackflow-memory-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'memory.db'}"
os.environ.setdefault("SECRET_KEY", "demo-memory-secret")

API_ROOT = Path(__file__).resolve().parents[1] / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import database  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

database.DB_DIR = str(_TMP)
database.DB_PATH = str(_TMP / "users.json")

from app.core.security import create_token, hash_password  # noqa: E402
from app.agent.memory import intent, service  # noqa: E402
from app.agent.memory.models import (  # noqa: E402
    AgentMemoryAudit,
    AgentMemoryEntry,
    AgentMemoryProposal,
    create_agent_memory_tables,
)
from app.agent.memory.scopes import normalize_scope  # noqa: E402
from app.agent.memory.schemas import MemoryProposalDraft  # noqa: E402
from app.agent.runner import AgentResult  # noqa: E402
from app.main import create_app  # noqa: E402

STATE = {
    "mode": "answer",
    "decision": "unrelated",
    "last_memory": [],
}


def _user(email: str, role: str) -> tuple[str, str]:
    db = database.get_tinydb()
    doc_id = db.table("users").insert(
        {
            "email": email,
            "hashed_password": hash_password("demo12345"),
            "is_active": True,
            "role": role,
            "created_at": "2026-11-14T00:00:00+00:00",
        }
    )
    db.close()
    return str(doc_id), create_token({"sub": str(doc_id), "role": role})


def _proposal(
    *,
    memory_type: str,
    scope: dict,
    fact: str,
    quote: str,
) -> dict:
    normalized = normalize_scope(scope, memory_type)
    return MemoryProposalDraft(
        memory_type=memory_type,
        scope=normalized,
        fact=fact,
        reason="Corrección aportada por el usuario",
        source_quote=quote,
    ).model_dump()


def fake_run_agent(question: str, **kwargs) -> AgentResult:
    STATE["last_memory"] = kwargs.get("memory_context") or []
    mode = STATE["mode"]
    proposal = None
    if mode == "propose_carrier":
        proposal = _proposal(
            memory_type="carrier_rule",
            scope={
                "tipo": "carrier",
                "carrier": "SEUR",
                "pais": "ES",
                "zona": "rural",
            },
            fact=(
                "SEUR ya no cubre la zona rural de Zaragoza; usar el carrier "
                "local desde el mes pasado."
            ),
            quote="SEUR ya no cubre esa zona rural de Zaragoza",
        )
        answer = "Entendido: SEUR ya no cubre esa zona rural de Zaragoza."
    elif mode == "propose_client":
        proposal = _proposal(
            memory_type="client_preference",
            scope={"tipo": "client", "cliente": "cosméticos"},
            fact=(
                "El cliente de cosméticos quiere el desglose de devoluciones "
                "primero en su reporte mensual."
            ),
            quote="siempre quiere su reporte mensual con el desglose de devoluciones primero",
        )
        answer = "Anotado: el cliente de cosméticos prefiere devoluciones primero."
    elif mode == "propose_address":
        proposal = _proposal(
            memory_type="carrier_rule",
            scope={
                "tipo": "carrier",
                "carrier": "SEUR",
                "pais": "ES",
                "zona": "rural",
            },
            fact="La entrega es en Calle Mayor 12, piso 3.",
            quote="SEUR ya no cubre esa zona rural de Zaragoza",
        )
        answer = "Entendido."
    else:
        facts = [item.get("fact") for item in STATE["last_memory"]]
        if facts:
            answer = "Según la memoria aprobada: " + " ".join(facts)
        else:
            answer = f"Respuesta a: {question} (sin memoria relevante)"
    return AgentResult(
        run_id=f"run-{mode}",
        status="ok",
        answer=answer,
        error=None,
        trace_path="/tmp/demo-trace.json",
        memory_proposal=proposal,
        memory_used=bool(STATE["last_memory"]),
    )


def fake_intent_chat(messages, **kwargs):
    decision = STATE["decision"]
    return (
        {
            "decision": decision,
            "confianza": 0.95,
            "propuesta_editada": None,
            "pregunta_restante": None,
            "motivo": "demo",
        },
        "{}",
    )


def _post(client: TestClient, token: str, message: str, session_id: str) -> dict:
    response = client.post(
        "/agent/chat",
        json={"message": message, "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    return {"status": response.status_code, "body": response.json()}


def _snapshot() -> dict:
    with Session(database.engine) as session:
        entries = session.exec(select(AgentMemoryEntry)).all()
        proposals = session.exec(select(AgentMemoryProposal)).all()
        audit = session.exec(select(AgentMemoryAudit)).all()
    return {
        "entries": [
            {
                "id": item.id,
                "memory_type": item.memory_type,
                "scope_key": item.scope_key,
                "fact": item.fact,
                "status": item.status,
                "version": item.version,
            }
            for item in entries
        ],
        "proposals": [
            {
                "id": item.id,
                "user_id": item.user_id,
                "memory_type": item.memory_type,
                "fact": item.fact,
                "status": item.status,
                "decision_label": item.decision_label,
                "decision_message": item.decision_message,
                "resulting_entry_id": item.resulting_entry_id,
            }
            for item in proposals
        ],
        "audit": [
            {
                "action": item.action,
                "actor_user_id": item.actor_user_id,
                "proposal_id": item.proposal_id,
                "entry_id": item.entry_id,
                "origin_message": item.origin_message,
                "detail": item.detail,
            }
            for item in audit
        ],
    }


def main() -> int:
    service.run_agent = fake_run_agent
    intent.chat_json = fake_intent_chat
    create_agent_memory_tables(database.engine)
    client = TestClient(create_app())
    admin_id, admin_token = _user("memory-demo@trackflow.com", "manager")
    other_id, other_token = _user("memory-reject@trackflow.com", "manager")

    cycles = {}

    STATE["mode"] = "propose_carrier"
    cycles["approved_step_1_proposal"] = _post(
        client,
        admin_token,
        (
            "En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que "
            "usar el carrier local desde el mes pasado."
        ),
        "demo-approved",
    )
    STATE["decision"] = "approve"
    cycles["approved_step_2_confirmation"] = _post(
        client, admin_token, "sí, guárdalo", "demo-approved"
    )
    STATE["mode"] = "answer"
    cycles["approved_step_3_future_use"] = _post(
        client,
        admin_token,
        "¿Qué carrier usamos para la zona rural de Zaragoza?",
        "demo-approved",
    )

    STATE["mode"] = "propose_client"
    cycles["rejected_step_1_proposal"] = _post(
        client,
        other_token,
        (
            "El cliente de cosméticos siempre quiere su reporte mensual con "
            "el desglose de devoluciones primero, antes que el volumen de "
            "envíos."
        ),
        "demo-rejected",
    )
    STATE["decision"] = "reject"
    cycles["rejected_step_2_confirmation"] = _post(
        client,
        other_token,
        "no, eso era solo para esta campaña",
        "demo-rejected",
    )
    STATE["mode"] = "answer"
    cycles["rejected_step_3_future_use"] = _post(
        client,
        other_token,
        "¿Cómo quiere el reporte el cliente de cosméticos?",
        "demo-rejected",
    )

    STATE["mode"] = "propose_address"
    cycles["blocked_forbidden_address"] = _post(
        client,
        other_token,
        (
            "La entrega de SEUR en la zona rural de Zaragoza se hace en "
            "Calle Mayor 12, piso 3."
        ),
        "demo-blocked",
    )

    output = {
        "cycles": cycles,
        "memory_snapshot": _snapshot(),
        "user_ids": {"approver": admin_id, "rejecter": other_id},
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
