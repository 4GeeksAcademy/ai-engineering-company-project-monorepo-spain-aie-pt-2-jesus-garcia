"""Endpoint de consulta a la base de conocimiento (RAG).

La ruta es la frontera de seguridad de este caso de uso: valida y sanea la
pregunta antes de invocar al modelo, aísla los chunks recuperados (contenido
externo no confiable) y aplica rate limiting por usuario. La lógica RAG vive
en ``data.pipelines.rag`` y no se duplica aquí.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.agent.harness.external import isolate_context
from app.agent.harness.injection import detect_injection
from app.agent.harness.observability import (
    ACTION_BLOCKED,
    CATEGORY_SECURITY,
    GuardrailEvent,
    question_hash,
    safe_snippet,
)
from app.agent.harness.observability import metrics as guard_metrics
from app.core.dependencies import require_manager
from app.core.rate_limit import enforce_rate_limit
from data.pipelines.rag import generate_answer, retrieve
from data.process.rag_config import RagConfigurationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

INJECTION_REFUSAL = (
    "No puedo cambiar mis instrucciones ni revelar configuración interna. "
    "Reformula la consulta sobre políticas de TrackFlow."
)


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
    request: Request,
    current_user: dict = Depends(require_manager),
) -> KnowledgeQueryResponse:
    enforce_rate_limit(
        request,
        bucket="knowledge:query",
        limit=30,
        window_seconds=60,
        identifier=str(current_user.get("id") or ""),
    )

    match = detect_injection(payload.question)
    if match is not None:
        guard_metrics.record(
            GuardrailEvent(
                guard="knowledge_injection_guard",
                category=CATEGORY_SECURITY,
                action=ACTION_BLOCKED,
                reason=match.reason,
                snippet=safe_snippet(payload.question),
                question_sha256=question_hash(payload.question),
            )
        )
        return KnowledgeQueryResponse(answer=INJECTION_REFUSAL)

    try:
        context = isolate_context(
            retrieve(payload.question),
            log=True,
        )
        answer = generate_answer(payload.question, context)
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
