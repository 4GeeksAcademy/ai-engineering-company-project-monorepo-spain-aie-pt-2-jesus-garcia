"""Generación con auto-evaluación de memoria en una sola llamada al LLM.

El modelo devuelve la respuesta visible y, si aplica, una propuesta de memoria.
No hay un segundo agente ni una segunda llamada en la ruta RAG: el mismo
generador del agente produce ambos campos.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from data.pipelines import rag

from . import config
from .llm import chat_json, json_or_raw_answer
from .prompts import build_generation_messages, format_memory_context
from .scopes import normalize_scope
from .schemas import GenerationOutcome, MemoryProposalDraft
from .validation import validate_proposal

logger = logging.getLogger(__name__)

JsonChat = Callable[..., tuple[dict | None, str]]

_CONFIRMATION_PREFIXES = (
    "¿quieres que lo recuerde",
    "¿quieres que recuerde",
)
_CONFIRMATION_TAIL_RE = re.compile(
    r"\s*¿[^?]{0,240}(?:recuerd|memoria|guarde|registre|apunte)[^?]*\?\s*$",
    re.IGNORECASE,
)


def parse_proposal(
    data: dict | None,
    message: str,
) -> tuple[MemoryProposalDraft | None, str | None]:
    """Convierte el bloque ``propuesta_memoria`` en un borrador validado."""

    if not isinstance(data, dict):
        return None, None

    memory_type = (
        data.get("tipo")
        or data.get("memory_type")
        or data.get("type")
        or ""
    )
    memory_type = str(memory_type).strip()
    if memory_type not in config.MEMORY_TYPES:
        return None, "invalid_type"

    scope_raw = (
        data.get("alcance")
        or data.get("scope")
        or data.get("scope_raw")
        or {}
    )
    scope = normalize_scope(scope_raw if isinstance(scope_raw, dict) else {}, memory_type)
    if scope is None:
        return None, "invalid_scope"

    fact = str(data.get("hecho") or data.get("fact") or "").strip()
    reason_raw = data.get("motivo") or data.get("reason")
    reason = str(reason_raw).strip() if reason_raw else None
    quote = str(
        data.get("cita_origen")
        or data.get("source_quote")
        or data.get("quote")
        or ""
    ).strip()

    draft = MemoryProposalDraft(
        memory_type=memory_type,  # type: ignore[arg-type]
        scope=scope,
        fact=fact,
        reason=reason,
        source_quote=quote,
    )
    issue = validate_proposal(draft, message)
    if not issue.ok:
        return None, issue.code
    return draft, None


def strip_confirmation_question(answer: str) -> str:
    """Evita duplicar la pregunta de confirmación que añade el servicio."""

    text = (answer or "").strip()
    for prefix in _CONFIRMATION_PREFIXES:
        index = text.lower().find(prefix)
        if index > 0:
            text = text[:index].rstrip()
    text = _CONFIRMATION_TAIL_RE.sub("", text).rstrip()
    return text


def generate_with_memory(
    question: str,
    context: list[dict],
    memory_context: list[dict] | None = None,
    *,
    llm: JsonChat | None = None,
) -> GenerationOutcome:
    question = question.strip()
    if not question:
        raise ValueError("La pregunta no puede estar vacía.")
    if not context:
        return GenerationOutcome(answer=rag.NO_CONTEXT_ANSWER)

    messages = build_generation_messages(
        question,
        context,
        memory_context or [],
    )
    call = llm or chat_json
    parsed, raw = call(messages, max_tokens=1_100, temperature=0.1)

    if parsed is None:
        answer = json_or_raw_answer(raw)
        return GenerationOutcome(
            answer=strip_confirmation_question(answer),
            proposal=None,
            validation_error="json_parse_error",
            json_ok=False,
        )

    answer_raw = parsed.get("respuesta") or parsed.get("answer")
    if not isinstance(answer_raw, str) or not answer_raw.strip():
        answer = json_or_raw_answer(raw)
        return GenerationOutcome(
            answer=strip_confirmation_question(answer),
            proposal=None,
            validation_error="missing_answer",
            json_ok=False,
        )

    proposal_raw = (
        parsed.get("propuesta_memoria")
        or parsed.get("memory_proposal")
    )
    proposal, validation_error = parse_proposal(proposal_raw, question)
    return GenerationOutcome(
        answer=strip_confirmation_question(answer_raw),
        proposal=proposal,
        validation_error=validation_error,
        json_ok=True,
    )


def memory_notes(memory_context: list[dict] | None, *, limit: int = 2) -> str:
    """Nota determinista para respuestas de tool con memoria relevante."""

    entries = list(memory_context or [])[:limit]
    if not entries:
        return ""
    lines = [f"- {entry.get('fact', '')}" for entry in entries if entry.get("fact")]
    if not lines:
        return ""
    return "Contexto recordado:\n" + "\n".join(lines)


def answer_uses_memory(
    answer: str, memory_context: list[dict] | None
) -> bool:
    """Heurística para trazar si la respuesta se apoyó en la memoria."""

    if not answer:
        return False
    answer_tokens = set(
        token
        for token in re.findall(r"[a-zA-Z0-9áéíóúüñÁÉÍÓÚÜÑ]+", answer.lower())
        if len(token) >= 4
    )
    if not answer_tokens:
        return False
    for entry in memory_context or []:
        fact_tokens = {
            token
            for token in re.findall(
                r"[a-zA-Z0-9áéíóúüñÁÉÍÓÚÜÑ]+",
                str(entry.get("fact") or "").lower(),
            )
            if len(token) >= 4
        }
        if len(answer_tokens & fact_tokens) >= 2:
            return True
    return False


def answer_from_memory(memory_context: list[dict] | None) -> str:
    """Respuesta sin LLM cuando el RAG no tiene contexto pero sí la memoria."""

    entries = list(memory_context or [])
    if not entries:
        return rag.NO_CONTEXT_ANSWER
    lines = [f"- {entry.get('fact', '')}" for entry in entries if entry.get("fact")]
    if not lines:
        return rag.NO_CONTEXT_ANSWER
    return (
        "No encuentro esa información en la base de conocimiento de TrackFlow, "
        "pero la memoria aprobada indica:\n" + "\n".join(lines) +
        "\n\nConfirma los detalles con el equipo responsable antes de "
        "trasladarlos a un cliente."
    )


def describe_memory_context(memory_context: list[dict] | None) -> str:
    """Representación compacta para prompts/trazas (nunca datos prohibidos)."""

    return format_memory_context(memory_context or [])


__all__ = [
    "answer_from_memory",
    "answer_uses_memory",
    "describe_memory_context",
    "generate_with_memory",
    "memory_notes",
    "parse_proposal",
    "strip_confirmation_question",
]
