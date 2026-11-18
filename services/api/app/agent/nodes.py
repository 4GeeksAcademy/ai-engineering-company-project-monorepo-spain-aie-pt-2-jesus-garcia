"""Nodos del grafo del agente: una responsabilidad por nodo.

Los nodos ``retrieve`` y ``generate`` reutilizan el pipeline RAG existente
(``data/pipelines/rag.py``) sin duplicarlo y sin invocar ``query()``: la
recuperación y la generación se ejecutan en pasos separados y trazables.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from data.pipelines import rag

from .state import AgentState

logger = logging.getLogger(__name__)

SAFE_ERROR_MESSAGE = (
    "No se pudo completar la consulta en este momento. "
    "Inténtalo de nuevo en unos minutos."
)

Retriever = Callable[[str], list[dict]]
Generator = Callable[[str, list[dict]], str]


def receive_question(state: AgentState) -> dict:
    """Normaliza la pregunta y decide si merece la pena recuperar contexto."""
    raw_question = state.get("question")
    question = raw_question.strip() if isinstance(raw_question, str) else ""
    if not question:
        logger.warning("Pregunta vacía: se evita la recuperación y la generación.")
        return {
            "question": "",
            "status": "invalid_question",
            "error": "La pregunta no puede estar vacía.",
        }
    return {"question": question, "status": "ok", "error": None}


def make_retrieve_node(retriever: Retriever | None = None) -> Callable[[AgentState], dict]:
    """Construye el nodo que ejecuta ``retrieve`` sobre la base de conocimiento."""
    retrieve = retriever or rag.retrieve

    def retrieve_node(state: AgentState) -> dict:
        question = state.get("question") or ""
        if state.get("status") == "invalid_question" or not question:
            # Defensa: nunca se recupera sin una pregunta válida.
            return {"context": [], "status": "invalid_question"}

        try:
            context = retrieve(question)
        except Exception:  # noqa: BLE001 - se reporta como fallo controlado
            logger.exception("Fallo al recuperar contexto para la pregunta")
            return {"context": [], "status": "error", "error": SAFE_ERROR_MESSAGE}

        return {"context": list(context), "status": "ok", "error": None}

    return retrieve_node


def make_generate_node(generator: Generator | None = None) -> Callable[[AgentState], dict]:
    """Construye el nodo que genera la respuesta con el contexto ya recuperado."""
    generate = generator or rag.generate_answer

    def generate_node(state: AgentState) -> dict:
        question = state.get("question") or ""
        context = state.get("context") or []
        if not context:
            # El enrutado ya evita este caso; se mantiene como red de seguridad
            # para que jamás se llame al LLM sin contexto.
            return {"answer": rag.NO_CONTEXT_ANSWER, "status": "no_context"}

        try:
            answer = generate(question, context)
        except Exception:  # noqa: BLE001 - se reporta como fallo controlado
            logger.exception("Fallo al generar la respuesta RAG")
            return {"status": "error", "error": SAFE_ERROR_MESSAGE}

        if not isinstance(answer, str) or not answer.strip():
            logger.error("El generador devolvió una respuesta vacía o no textual.")
            return {"status": "error", "error": SAFE_ERROR_MESSAGE}

        return {"answer": answer.strip(), "status": "ok", "error": None}

    return generate_node


def no_context_node(state: AgentState) -> dict:
    """Responde con honestidad cuando la recuperación no supera el umbral."""
    return {"answer": rag.NO_CONTEXT_ANSWER, "status": "no_context", "error": None}


def fail_node(state: AgentState) -> dict:
    """Salida terminal segura para preguntas inválidas o fallos internos."""
    status = state.get("status")
    if status not in ("invalid_question", "error"):
        status = "error"
    return {
        "status": status,
        "error": state.get("error") or SAFE_ERROR_MESSAGE,
        "answer": "",
    }
