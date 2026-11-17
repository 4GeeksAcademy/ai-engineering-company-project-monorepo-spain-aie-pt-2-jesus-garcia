"""Evaluación de memoria para respuestas deterministas (tool / sin contexto).

Es la única llamada al LLM en esos turnos; la respuesta visible ya se construyó
sin LLM. Solo se invoca cuando el gate determinista detecta un candidato.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from .generation import parse_proposal
from .llm import chat_json
from .prompts import build_evaluation_messages
from .schemas import EvaluationOutcome

logger = logging.getLogger(__name__)

JsonChat = Callable[..., tuple[dict | None, str]]


def evaluate_interaction(
    *,
    question: str,
    answer: str,
    tool_result: dict | None = None,
    memory_context: list[dict] | None = None,
    llm: JsonChat | None = None,
) -> EvaluationOutcome:
    messages = build_evaluation_messages(
        question=question,
        answer=answer,
        tool_result=tool_result,
        memory_context=memory_context or [],
    )
    call = llm or chat_json
    parsed, _raw = call(messages, max_tokens=700, temperature=0.0)
    if parsed is None:
        return EvaluationOutcome(
            proposal=None, validation_error="json_parse_error", json_ok=False
        )

    proposal_raw = parsed.get("propuesta_memoria") or parsed.get(
        "memory_proposal"
    )
    proposal, validation_error = parse_proposal(proposal_raw, question)
    return EvaluationOutcome(
        proposal=proposal,
        validation_error=validation_error,
        json_ok=True,
    )


__all__ = ["evaluate_interaction"]
