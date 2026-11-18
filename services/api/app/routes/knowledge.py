"""Endpoint de consulta a la base de conocimiento (RAG)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.core.dependencies import get_current_user
from data.pipelines.rag import query
from data.process.rag_config import RagConfigurationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("La pregunta no puede estar vacía.")
        return value


class KnowledgeQueryResponse(BaseModel):
    answer: str


@router.post(
    "/query",
    response_model=KnowledgeQueryResponse,
    summary="Responder una pregunta con la base de conocimiento de TrackFlow",
)
def knowledge_query(
    payload: KnowledgeQueryRequest,
    _=Depends(get_current_user),
) -> KnowledgeQueryResponse:
    try:
        answer = query(payload.question)
    except RagConfigurationError as exc:
        logger.error("RAG sin configuración: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="El asistente no está configurado. Contacta con el equipo técnico.",
        ) from exc
    except Exception as exc:
        logger.exception("Error generando una respuesta RAG")
        raise HTTPException(
            status_code=502,
            detail="No se pudo generar la respuesta. Inténtalo de nuevo.",
        ) from exc

    return KnowledgeQueryResponse(answer=answer)
