"""Orquestación del chat con memoria: pendiente → grafo → propuesta → respuesta.

El grafo decide y redacta; este servicio resuelve la propuesta pendiente,
lee el bloque de memoria, persiste la nueva propuesta y añade la pregunta de
confirmación en la misma respuesta. La base de datos nunca se toca desde los
nodos del grafo.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from ..runner import AgentRunError, run_agent
from . import config
from .intent import classify_intent
from .schemas import (
    MemoryProposalDraft,
    MemoryProposalView,
    MemoryResolutionView,
)
from .store import (
    chat_proposal_payload,
    create_proposal,
    get_pending,
    memory_session,
    proposal_view,
    read_memory,
    resolution_view,
    resolve_proposal,
)

logger = logging.getLogger(__name__)


@dataclass
class ChatMemory:
    pending_proposal: MemoryProposalView | None = None
    resolution: MemoryResolutionView | None = None
    blocked: str | None = None


@dataclass
class ChatResult:
    session_id: str
    run_id: str | None
    answer: str
    status: str
    error: str | None = None
    memory: ChatMemory | None = None


def _user_id(user: dict | None) -> str:
    if not user:
        return "anonymous"
    return str(user.get("id") or user.get("email") or "anonymous")


def _user_role(user: dict | None) -> str:
    return str((user or {}).get("role") or "user")


def _draft_from_dict(payload: dict) -> MemoryProposalDraft | None:
    try:
        return MemoryProposalDraft.model_validate(payload)
    except Exception:  # noqa: BLE001 - el grafo ya validó; defensa extra
        logger.warning("El grafo devolvió una propuesta de memoria no válida.")
        return None


def chat(
    message: str,
    *,
    user: dict | None = None,
    session_id: str | None = None,
    graph=None,
    trace_dir=None,
    intent_llm=None,
) -> ChatResult:
    text = (message or "").strip()
    session = session_id or str(uuid.uuid4())
    if not text:
        return ChatResult(
            session_id=session,
            run_id=None,
            answer="",
            status="invalid_question",
            error="La pregunta no puede estar vacía.",
        )

    user_id = _user_id(user)
    role = _user_role(user)
    memory = ChatMemory()
    question = text
    memory_context: list[dict] = []

    with memory_session() as db:
        pending = get_pending(db, user_id) if db is not None else None
        if pending is not None:
            outcome = classify_intent(
                text,
                chat_proposal_payload(pending),
                llm=intent_llm,
            )
            decision = outcome.decision
            remaining = decision.remaining_question
            if decision.decision in {"approve", "reject", "edit"}:
                resolved = resolve_proposal(
                    db,
                    pending.id,
                    user_id=user_id,
                    user_role=role,
                    decision=decision.decision,
                    decision_message=text,
                    edited_draft=decision.edited_proposal,
                    confidence=decision.confidence,
                )
                memory.resolution = resolution_view(
                    resolved, proposal_id=pending.id
                )
                if not resolved.ok and resolved.status == "awaiting_role":
                    return ChatResult(
                        session_id=session,
                        run_id=None,
                        answer=resolved.message,
                        status="ok",
                        memory=memory,
                    )
                question = remaining or ""
                if not question:
                    return ChatResult(
                        session_id=session,
                        run_id=None,
                        answer=resolved.message,
                        status="ok",
                        memory=memory,
                    )
            else:
                # Cambio de tema, ambigüedad o silencio: rechazo por defecto.
                resolved = resolve_proposal(
                    db,
                    pending.id,
                    user_id=user_id,
                    user_role=role,
                    decision="unrelated",
                    decision_message=text,
                    confidence=decision.confidence,
                )
                memory.resolution = resolution_view(
                    resolved, proposal_id=pending.id
                )
                question = text

        memory_context = (
            read_memory(db, question) if db is not None else []
        )

    try:
        result = run_agent(
            question,
            user=user,
            memory_context=memory_context,
            graph=graph,
            trace_dir=trace_dir,
        )
    except AgentRunError as exc:
        logger.error("La corrida del agente falló en el chat: %s", exc)
        return ChatResult(
            session_id=session,
            run_id=None,
            answer="",
            status="error",
            error=str(exc),
            memory=memory,
        )
    except Exception:  # noqa: BLE001 - el detalle no sale al cliente
        logger.exception("Error inesperado en el chat del agente")
        return ChatResult(
            session_id=session,
            run_id=None,
            answer="",
            status="error",
            error="No se pudo completar la consulta.",
            memory=memory,
        )

    answer = result.answer
    if (
        memory.resolution is not None
        and memory.resolution.decision in {"approve", "reject", "edit"}
    ):
        answer = f"{memory.resolution.message}\n\n{answer}"
    if result.memory_validation_error:
        memory.blocked = result.memory_validation_error

    if result.memory_proposal:
        with memory_session() as db:
            if db is not None:
                draft = _draft_from_dict(result.memory_proposal)
                if draft is not None:
                    created = create_proposal(
                        db,
                        session_id=session,
                        user_id=user_id,
                        run_id=result.run_id,
                        draft=draft,
                        origin_message=question,
                    )
                    if created.created and created.proposal is not None:
                        answer = f"{answer}\n\n{config.MEMORY_QUESTION}"
                        memory.pending_proposal = proposal_view(
                            created.proposal
                        )
                    elif created.reason == "validation_failed":
                        memory.blocked = created.validation_code
                    elif created.reason == "already_pending":
                        memory.blocked = "already_pending"

    return ChatResult(
        session_id=session,
        run_id=result.run_id,
        answer=answer,
        status=result.status,
        error=result.error,
        memory=memory if any(
            (
                memory.pending_proposal,
                memory.resolution,
                memory.blocked,
            )
        ) else None,
    )
