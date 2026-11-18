"""Clasificador de intención sobre una propuesta de memoria pendiente.

Nunca usa coincidencia ingenua de texto: el LLM devuelve una etiqueta
estructurada y el sistema falla en cerrado (``unrelated`` → rechazo) ante
cualquier duda, error o baja confianza.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from . import config
from .generation import parse_proposal
from .llm import chat_json
from .prompts import build_intent_messages
from .schemas import IntentDecision, IntentOutcome

logger = logging.getLogger(__name__)

JsonChat = Callable[..., tuple[dict | None, str]]

_DECISIONS = {"approve", "reject", "edit", "unrelated"}


def _confidence(value) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _remaining(value) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:1_000]


def classify_intent(
    message: str,
    proposal: dict,
    *,
    llm: JsonChat | None = None,
    min_confidence: float | None = None,
) -> IntentOutcome:
    """Devuelve una decisión tipada; por defecto, rechazo."""

    messages = build_intent_messages(message=message, proposal=proposal)
    call = llm or chat_json
    try:
        parsed, _raw = call(messages, max_tokens=700, temperature=0.0)
    except Exception:  # noqa: BLE001 - se falla en cerrado
        logger.exception("Fallo del clasificador de intención de memoria")
        return IntentOutcome(
            decision=IntentDecision(decision="unrelated", confidence=1.0),
            json_ok=False,
            error="classifier_error",
        )

    if parsed is None:
        return IntentOutcome(
            decision=IntentDecision(decision="unrelated", confidence=1.0),
            json_ok=False,
            error="invalid_json",
        )

    raw_decision = str(
        parsed.get("decision") or parsed.get("etiqueta") or "unrelated"
    ).lower()
    if raw_decision not in _DECISIONS:
        raw_decision = "unrelated"
    confidence = _confidence(
        parsed.get("confianza", parsed.get("confidence", 0.0))
    )
    threshold = (
        config.INTENT_MIN_CONFIDENCE
        if min_confidence is None
        else min_confidence
    )

    if raw_decision not in {"unrelated"} and confidence < threshold:
        return IntentOutcome(
            decision=IntentDecision(
                decision="unrelated",
                confidence=confidence,
                reason="low_confidence",
            )
        )

    remaining = _remaining(
        parsed.get("pregunta_restante", parsed.get("remaining_question"))
    )
    if raw_decision == "unrelated":
        remaining = None
    elif remaining and remaining.strip() == (message or "").strip():
        remaining = None

    if raw_decision == "edit":
        edited_raw = parsed.get("propuesta_editada") or parsed.get(
            "edited_proposal"
        )
        edited, error = parse_proposal(edited_raw, message)
        if edited is None:
            return IntentOutcome(
                decision=IntentDecision(
                    decision="unrelated",
                    confidence=confidence,
                    reason=f"invalid_edit:{error or 'missing'}",
                )
            )
        return IntentOutcome(
            decision=IntentDecision(
                decision="edit",
                confidence=confidence,
                edited_proposal=edited,
                remaining_question=remaining,
                reason=str(parsed.get("motivo") or parsed.get("reason") or ""),
            )
        )

    return IntentOutcome(
        decision=IntentDecision(
            decision=raw_decision,  # type: ignore[arg-type]
            confidence=confidence,
            remaining_question=remaining,
            reason=str(parsed.get("motivo") or parsed.get("reason") or ""),
        )
    )


__all__ = ["classify_intent"]
