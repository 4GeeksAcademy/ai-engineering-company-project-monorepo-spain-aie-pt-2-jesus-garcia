"""Resumen HTTP de los guardrails del agente.

El endpoint lee los contadores en memoria que alimenta
``app.agent.harness.observability``. Cada bloqueo, redirección, corrección o
saneamiento queda registrado con su tipo de fallo (structural/content/security).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.agent.harness.observability import metrics
from app.core.dependencies import require_manager

router = APIRouter(prefix="/agent/harness", tags=["agent-harness"])


class GuardrailEventView(BaseModel):
    guard: str
    category: str
    action: str
    reason: str
    run_id: str | None = None
    session_id: str | None = None
    snippet: str = ""
    question_sha256: str | None = None
    timestamp: str


class GuardrailStatsResponse(BaseModel):
    since: str
    session_id: str | None = None
    totals: dict[str, int]
    by_category: dict[str, int]
    by_guard: dict[str, int]
    by_reason: dict[str, int]
    recent: list[GuardrailEventView]


@router.get(
    "/stats",
    response_model=GuardrailStatsResponse,
    summary="Resumen de activaciones de los guardrails del agente",
)
def agent_harness_stats(
    session_id: str | None = Query(
        default=None,
        max_length=100,
        description="Filtra por sesión de conversación.",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_manager),
) -> GuardrailStatsResponse:
    snapshot = metrics.snapshot(session_id=session_id, limit=limit)
    return GuardrailStatsResponse(**snapshot)
