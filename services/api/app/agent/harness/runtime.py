"""Borde de ejecución del agente: input guard + output guard.

``run_agent`` llama a :func:`screen_input` antes de invocar el grafo y a
:func:`validate_output` al terminar. Así todos los puntos de entrada
(``/agent/query`` y ``/agent/chat``) comparten exactamente las mismas capas,
sin duplicar lógica en los routers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .general import answer_general
from .injection import detect_injection
from .observability import (
    ACTION_BLOCKED,
    ACTION_CORRECTED,
    ACTION_REDIRECTED,
    ACTION_SANITIZED,
    CATEGORY_CONTENT,
    CATEGORY_SECURITY,
    CATEGORY_STRUCTURAL,
    GuardrailEvent,
    metrics,
    question_hash,
    safe_snippet,
)
from .orders import (
    ORDER_AUTH_UNAVAILABLE,
    ORDER_UNAUTHORIZED,
    OrderAuthorization,
    OrderResolver,
    authorize_orders,
    extract_order_refs,
)
from .output import validate_output
from .scope import (
    OUT_OF_DOMAIN_REDIRECT,
    PERSONAL_USE_REFUSAL,
    classify_scope,
)

MAX_QUESTION_CHARS = 2_000

INJECTION_REFUSAL = (
    "No puedo cambiar mis instrucciones ni actuar como un asistente sin "
    "reglas. Soy el agente de soporte logístico de TrackFlow y mi función es "
    "ayudarte con envíos, devoluciones e incidencias. ¿Tienes alguna consulta "
    "sobre tu pedido?"
)

_COUNTRY_LABELS = {"US": "Estados Unidos", "ES": "España"}

_US_LOCATION_RE = re.compile(
    r"\b(?:los\s+angeles|los\s+ángeles|estados\s+unidos|ee\.?\s*uu\.?|"
    r"eeuu|usa|california|nueva\s+york|new\s+york|miami)\b",
    re.IGNORECASE,
)
_ES_LOCATION_RE = re.compile(
    r"\b(?:espana|españa|zaragoza|madrid|aragon|aragón|barcelona|"
    r"valencia|sevilla)\b",
    re.IGNORECASE,
)
_ES_POLICY_RE = re.compile(
    r"\b(?:politica|política)\b.{0,50}"
    r"\b(?:espana|españa|espanol|español|espanola|española)\b"
    r"|\b(?:espana|españa|espanol|español|espanola|española)\b.{0,50}"
    r"\b(?:politica|política)\b",
    re.IGNORECASE,
)
_US_POLICY_RE = re.compile(
    r"\b(?:politica|política)\b.{0,50}"
    r"\b(?:estados\s+unidos|ee\.?\s*uu\.?|usa|estadounidense)\b"
    r"|\b(?:estados\s+unidos|ee\.?\s*uu\.?|usa|estadounidense)\b.{0,50}"
    r"\b(?:politica|política)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InputGuardResult:
    action: Literal["allow", "blocked", "redirected", "corrected"]
    question: str
    answer: str | None = None
    guard: str | None = None
    category: str | None = None
    reason: str | None = None
    context: dict = field(default_factory=dict)
    events: tuple[GuardrailEvent, ...] = ()

    @property
    def is_blocked(self) -> bool:
        return self.action == "blocked"

    @property
    def has_deterministic_answer(self) -> bool:
        return self.action == "redirected" and bool(self.answer)


def _event(
    *,
    guard: str,
    category: str,
    action: str,
    reason: str,
    question: str,
    run_id: str | None,
    session_id: str | None,
) -> GuardrailEvent:
    return GuardrailEvent(
        guard=guard,
        category=category,
        action=action,
        reason=reason,
        run_id=run_id,
        session_id=session_id,
        snippet=safe_snippet(question),
        question_sha256=question_hash(question),
    )


def _clean_controls(text: str) -> tuple[str, bool]:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    changed = cleaned != text
    return re.sub(r"[ \t]+", " ", cleaned).strip(), changed


_POLICY_PHRASE_RE = re.compile(
    r"\b(?:politica|política)\b.{0,50}?"
    r"\b(?:espana|españa|espanol|español|estados\s+unidos|"
    r"ee\.?\s*uu\.?|usa|estadounidense)\b",
    re.IGNORECASE,
)


def _strip_policy_phrase(question: str) -> str:
    """Quita "política de España" para no confundirla con la ubicación real."""

    return _POLICY_PHRASE_RE.sub(" ", question or "")


def _country_from_question(question: str) -> str | None:
    text = _strip_policy_phrase(question)
    if _ES_LOCATION_RE.search(text):
        return "ES"
    if _US_LOCATION_RE.search(text):
        return "US"
    return None


def _requested_policy_country(question: str) -> str | None:
    if _ES_POLICY_RE.search(question or ""):
        return "ES"
    if _US_POLICY_RE.search(question or ""):
        return "US"
    return None


def _policy_correction(
    question: str,
    *,
    actual_country: str | None,
) -> tuple[str | None, str | None]:
    """Devuelve (país real, nota de corrección) si se intentan mezclar políticas."""

    requested = _requested_policy_country(question)
    if requested is None:
        return actual_country, None

    actual = actual_country or _country_from_question(question)
    if actual is None or actual == requested:
        return actual, None

    actual_label = _COUNTRY_LABELS.get(actual, actual)
    requested_label = _COUNTRY_LABELS.get(requested, requested)
    correction = (
        f"El pedido consultado pertenece a {actual_label}. Aplica la política "
        f"de {actual_label} y no la de {requested_label}. Si el usuario "
        f"insiste en mezclar políticas, explica que no puedes hacerlo y "
        f"ofrece la alternativa correcta."
    )
    return actual, correction


def screen_input(
    question: str,
    *,
    user: dict | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    order_resolver: OrderResolver | None = None,
    security_only: bool = False,
    log: bool = True,
) -> InputGuardResult:
    """Aplica las capas de entrada y devuelve la decisión del harness."""

    raw = question if isinstance(question, str) else ""
    cleaned, had_controls = _clean_controls(raw)
    events: list[GuardrailEvent] = []

    if not cleaned:
        event = _event(
            guard="structural_guard",
            category=CATEGORY_STRUCTURAL,
            action=ACTION_BLOCKED,
            reason="empty_question",
            question=raw,
            run_id=run_id,
            session_id=session_id,
        )
        if log:
            metrics.record(event)
        return InputGuardResult(
            action="blocked",
            question="",
            answer=(
                "La consulta está vacía. Escribe una pregunta sobre un envío, "
                "una devolución o una incidencia de TrackFlow."
            ),
            guard=event.guard,
            category=event.category,
            reason=event.reason,
            events=(event,),
        )

    if len(cleaned) > MAX_QUESTION_CHARS:
        event = _event(
            guard="structural_guard",
            category=CATEGORY_STRUCTURAL,
            action=ACTION_BLOCKED,
            reason="question_too_long",
            question=cleaned,
            run_id=run_id,
            session_id=session_id,
        )
        if log:
            metrics.record(event)
        return InputGuardResult(
            action="blocked",
            question=cleaned,
            answer=(
                "La consulta es demasiado larga. Resúmela en menos de "
                f"{MAX_QUESTION_CHARS} caracteres."
            ),
            guard=event.guard,
            category=event.category,
            reason=event.reason,
            events=(event,),
        )

    if had_controls:
        event = _event(
            guard="structural_guard",
            category=CATEGORY_STRUCTURAL,
            action=ACTION_SANITIZED,
            reason="control_characters",
            question=cleaned,
            run_id=run_id,
            session_id=session_id,
        )
        if log:
            metrics.record(event)
        events.append(event)

    injection = detect_injection(cleaned)
    if injection is not None:
        event = _event(
            guard="injection_guard",
            category=CATEGORY_SECURITY,
            action=ACTION_BLOCKED,
            reason=injection.reason,
            question=cleaned,
            run_id=run_id,
            session_id=session_id,
        )
        if log:
            metrics.record(event)
        events.append(event)
        return InputGuardResult(
            action="blocked",
            question=cleaned,
            answer=INJECTION_REFUSAL,
            guard=event.guard,
            category=event.category,
            reason=event.reason,
            events=tuple(events),
        )

    refs = extract_order_refs(cleaned)
    authorization = OrderAuthorization()
    if refs:
        resolver = order_resolver
        if resolver is None and user:
            from .orders import SqlOrderResolver

            resolver = SqlOrderResolver()
        authorization = authorize_orders(refs, user, resolver)
        if authorization.error or authorization.unauthorized:
            reason = (
                "authorization_unavailable"
                if authorization.error
                else "order_not_authorized"
            )
            event = _event(
                guard="order_authorization_guard",
                category=CATEGORY_SECURITY,
                action=ACTION_BLOCKED,
                reason=reason,
                question=cleaned,
                run_id=run_id,
                session_id=session_id,
            )
            if log:
                metrics.record(event)
            events.append(event)
            return InputGuardResult(
                action="blocked",
                question=cleaned,
                answer=(
                    ORDER_AUTH_UNAVAILABLE
                    if authorization.error
                    else ORDER_UNAUTHORIZED
                ),
                guard=event.guard,
                category=event.category,
                reason=event.reason,
                events=tuple(events),
            )

    context: dict = {
        "authorized_orders": [owner.__dict__ for owner in authorization.authorized],
        "required_country": (
            authorization.authorized[0].country
            if authorization.authorized
            else None
        ),
    }

    scope = classify_scope(cleaned)
    if security_only:
        if scope.kind == "personal_use":
            event = _event(
                guard="personal_use_guard",
                category=CATEGORY_CONTENT,
                action=ACTION_BLOCKED,
                reason=scope.reason,
                question=cleaned,
                run_id=run_id,
                session_id=session_id,
            )
            if log:
                metrics.record(event)
            events.append(event)
            return InputGuardResult(
                action="blocked",
                question=cleaned,
                answer=PERSONAL_USE_REFUSAL,
                guard=event.guard,
                category=event.category,
                reason=event.reason,
                context=context,
                events=tuple(events),
            )
        return InputGuardResult(
            action="allow",
            question=cleaned,
            context=context,
            events=tuple(events),
        )

    if scope.kind == "personal_use":
        event = _event(
            guard="personal_use_guard",
            category=CATEGORY_CONTENT,
            action=ACTION_BLOCKED,
            reason=scope.reason,
            question=cleaned,
            run_id=run_id,
            session_id=session_id,
        )
        if log:
            metrics.record(event)
        events.append(event)
        return InputGuardResult(
            action="blocked",
            question=cleaned,
            answer=PERSONAL_USE_REFUSAL,
            guard=event.guard,
            category=event.category,
            reason=event.reason,
            context=context,
            events=tuple(events),
        )

    if scope.kind in ("casual", "general_logistics", "out_of_domain"):
        answer = (
            OUT_OF_DOMAIN_REDIRECT
            if scope.kind == "out_of_domain"
            else answer_general(cleaned, scope.kind)
        )
        event = _event(
            guard="scope_guard",
            category=CATEGORY_CONTENT,
            action=ACTION_REDIRECTED,
            reason=scope.reason,
            question=cleaned,
            run_id=run_id,
            session_id=session_id,
        )
        if log:
            metrics.record(event)
        events.append(event)
        return InputGuardResult(
            action="redirected",
            question=cleaned,
            answer=answer,
            guard=event.guard,
            category=event.category,
            reason=event.reason,
            context=context,
            events=tuple(events),
        )

    actual_country, correction = _policy_correction(
        cleaned,
        actual_country=context.get("required_country"),
    )
    if actual_country:
        context["required_country"] = actual_country
    if correction:
        context["policy_correction"] = correction
        event = _event(
            guard="policy_mixing_guard",
            category=CATEGORY_CONTENT,
            action=ACTION_CORRECTED,
            reason="policy_mixing",
            question=cleaned,
            run_id=run_id,
            session_id=session_id,
        )
        if log:
            metrics.record(event)
        events.append(event)
        return InputGuardResult(
            action="corrected",
            question=cleaned,
            guard=event.guard,
            category=event.category,
            reason=event.reason,
            context=context,
            events=tuple(events),
        )

    return InputGuardResult(
        action="allow",
        question=cleaned,
        context=context,
        events=tuple(events),
    )


__all__ = [
    "INJECTION_REFUSAL",
    "MAX_QUESTION_CHARS",
    "InputGuardResult",
    "screen_input",
    "validate_output",
]
