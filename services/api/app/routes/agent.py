"""Endpoint del agente RAG (grafo LangGraph).

El router no implementa lógica de negocio: invoca el grafo compilado y traduce
su estado final a HTTP. Cualquier detalle interno queda en los logs y en el
trace, nunca en la respuesta.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agent.graph import get_agent_graph
from app.agent.runner import AgentRunError, run_agent
from app.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

GENERIC_ERROR_DETAIL = (
    "No se pudo completar la consulta. Inténtalo de nuevo en unos minutos."
)

# Traducción transporte: estado del grafo → código HTTP.
_STATUS_TO_HTTP = {
    "invalid_question": 422,
    "error": 502,
}


# Se compila al importar el router: un problema estructural impide arrancar la
# API en lugar de aparecer en la primera petición.
get_agent_graph()


class AgentQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class AgentQueryResponse(BaseModel):
    answer: str
    run_id: str


@router.post(
    "/query",
    response_model=AgentQueryResponse,
    summary="Responder una pregunta con el agente RAG trazable",
)
def agent_query(
    payload: AgentQueryRequest,
    current_user: dict = Depends(get_current_user),
) -> AgentQueryResponse:
    try:
        result = run_agent(payload.question, user=current_user)
    except AgentRunError as exc:
        logger.error("La corrida del agente falló: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=GENERIC_ERROR_DETAIL,
        ) from exc
    except Exception as exc:  # noqa: BLE001 - nunca se expone el detalle interno
        logger.exception("Error inesperado invocando el grafo del agente")
        raise HTTPException(
            status_code=502,
            detail=GENERIC_ERROR_DETAIL,
        ) from exc

    status_code = _STATUS_TO_HTTP.get(result.status)
    if status_code is not None:
        raise HTTPException(
            status_code=status_code,
            detail=result.error or GENERIC_ERROR_DETAIL,
        )
    if not result.answer:
        raise HTTPException(status_code=502, detail=GENERIC_ERROR_DETAIL)

    return AgentQueryResponse(answer=result.answer, run_id=result.run_id)
