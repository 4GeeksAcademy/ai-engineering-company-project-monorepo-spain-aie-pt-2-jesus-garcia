"""Endpoints de chat con memoria y administración del store.

``/agent/query`` sigue siendo el endpoint stateless original. ``/agent/chat``
añade la conversación necesaria para resolver propuestas pendientes y mostrar
la pregunta de confirmación en la misma respuesta.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent.memory.schemas import (
    MemoryEntryView,
    MemoryProposalView,
    MemoryResolutionView,
)
from app.agent.memory.service import chat
from app.agent.memory.store import (
    consolidate,
    list_entries,
    list_proposals,
    memory_session,
    resolution_view,
    resolve_proposal,
    retire_entry,
)
from app.core.dependencies import get_current_user, require_manager

router = APIRouter(prefix="/agent", tags=["agent-memory"])

GENERIC_ERROR_DETAIL = (
    "No se pudo completar la consulta. Inténtalo de nuevo en unos minutos."
)


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4_000)
    session_id: str | None = Field(default=None, max_length=100)


class AgentChatMemoryResponse(BaseModel):
    pending_proposal: MemoryProposalView | None = None
    resolution: MemoryResolutionView | None = None
    blocked: str | None = None


class AgentChatResponse(BaseModel):
    session_id: str
    run_id: str | None = None
    answer: str
    memory: AgentChatMemoryResponse | None = None


class MemoryListResponse(BaseModel):
    entries: list[MemoryEntryView]


class ProposalAuditView(BaseModel):
    id: str
    session_id: str
    user_id: str
    run_id: str | None = None
    memory_type: str
    scope: dict
    scope_label: str
    fact: str
    reason: str | None = None
    status: str
    decision_label: str | None = None
    decision_confidence: float | None = None
    decision_message: str | None = None
    decision_at: str | None = None
    resulting_entry_id: str | None = None
    validation_code: str | None = None
    created_at: str | None = None


class ProposalListResponse(BaseModel):
    proposals: list[ProposalAuditView]


class RetireResponse(BaseModel):
    retired: bool


class ManagerDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"] = "approve"
    note: str | None = Field(default=None, max_length=500)


class ConsolidateResponse(BaseModel):
    counts: dict[str, int]


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    summary="Conversar con el agente y gestionar propuestas de memoria",
)
def agent_chat(
    payload: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
) -> AgentChatResponse:
    result = chat(
        payload.message,
        user=current_user,
        session_id=payload.session_id,
    )
    if result.status == "invalid_question":
        raise HTTPException(
            status_code=422,
            detail=result.error or "La pregunta no puede estar vacía.",
        )
    if result.status == "error":
        raise HTTPException(status_code=502, detail=GENERIC_ERROR_DETAIL)
    if not result.answer:
        raise HTTPException(status_code=502, detail=GENERIC_ERROR_DETAIL)

    memory = None
    if result.memory is not None:
        memory = AgentChatMemoryResponse(
            pending_proposal=result.memory.pending_proposal,
            resolution=result.memory.resolution,
            blocked=result.memory.blocked,
        )
    return AgentChatResponse(
        session_id=result.session_id,
        run_id=result.run_id,
        answer=result.answer,
        memory=memory,
    )


@router.get(
    "/memory",
    response_model=MemoryListResponse,
    summary="Consultar la memoria activa del agente",
)
def agent_memory_list(
    current_user: dict = Depends(get_current_user),
) -> MemoryListResponse:
    with memory_session() as session:
        entries = list_entries(session)
    return MemoryListResponse(entries=entries)


@router.get(
    "/memory/proposals",
    response_model=ProposalListResponse,
    summary="Auditoría de propuestas de memoria (manager/admin)",
)
def agent_memory_proposals(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict = Depends(require_manager),
) -> ProposalListResponse:
    with memory_session() as session:
        proposals = list_proposals(session, status=status, limit=limit)
    return ProposalListResponse(proposals=proposals)


@router.post(
    "/memory/proposals/{proposal_id}/approve",
    response_model=MemoryResolutionView,
    summary="Aprobar o rechazar una propuesta ajena (manager/admin)",
)
def agent_memory_manager_resolve(
    proposal_id: str,
    payload: ManagerDecisionRequest,
    current_user: dict = Depends(require_manager),
) -> MemoryResolutionView:
    with memory_session() as session:
        result = resolve_proposal(
            session,
            proposal_id,
            user_id=str(current_user.get("id") or ""),
            user_role=str(current_user.get("role") or "manager"),
            decision=payload.decision,
            decision_message=payload.note or "decisión de manager",
            confidence=1.0,
            allow_other_user=True,
        )
    if result.status == "not_found":
        raise HTTPException(status_code=404, detail="La propuesta no existe.")
    if result.status == "not_pending":
        raise HTTPException(
            status_code=409, detail="La propuesta ya está resuelta."
        )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.message)
    return resolution_view(result, proposal_id=proposal_id)


@router.post(
    "/memory/{entry_id}/retire",
    response_model=RetireResponse,
    summary="Retirar una entrada de memoria (manager/admin)",
)
def agent_memory_retire(
    entry_id: str,
    current_user: dict = Depends(require_manager),
) -> RetireResponse:
    with memory_session() as session:
        retired = retire_entry(
            session,
            entry_id,
            actor_user_id=str(current_user.get("id") or ""),
            reason="retirada manual",
        )
    if not retired:
        raise HTTPException(
            status_code=404,
            detail="La entrada no existe o no está activa.",
        )
    return RetireResponse(retired=True)


@router.post(
    "/memory/consolidate",
    response_model=ConsolidateResponse,
    summary="Ejecutar la consolidación de memoria (manager/admin)",
)
def agent_memory_consolidate(
    current_user: dict = Depends(require_manager),
) -> ConsolidateResponse:
    with memory_session() as session:
        counts = consolidate(session)
    return ConsolidateResponse(counts=counts)
