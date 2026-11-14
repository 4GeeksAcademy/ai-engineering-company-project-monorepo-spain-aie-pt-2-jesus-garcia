"""Validación de la respuesta antes de devolverla al usuario.

Comprueba cuatro familias de problemas:

1. **Formato**: respuesta vacía, demasiado larga, con caracteres de control o
   con JSON/código interno filtrado.
2. **Fuga de instrucciones**: el modelo copia el system prompt o el esquema
   interno de memoria.
3. **Datos sensibles del briefing**: tarifas negociadas con carriers,
   direcciones o rutas internas de almacenes, credenciales y datos personales.
4. **Alcance**: pedidos de otra sesión y mezcla de políticas de país.

Si algo falla, la respuesta se sustituye por un mensaje seguro y se registra el
evento con su categoría (content/security/structural).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .injection import normalize_text
from .observability import (
    ACTION_BLOCKED,
    CATEGORY_CONTENT,
    CATEGORY_SECURITY,
    CATEGORY_STRUCTURAL,
    GuardrailEvent,
    metrics,
    question_hash,
    safe_snippet,
)
from .orders import extract_order_refs
from .prompt import CX_SYSTEM_PROMPT
from .scope import REDIRECT_LINE

MAX_ANSWER_CHARS = 8_000

SAFE_OUTPUT_MESSAGE = (
    "No puedo mostrar esa información. Soy el agente de soporte logístico de "
    "TrackFlow y puedo ayudarte con envíos, devoluciones e incidencias."
)

COUNTRY_LABELS = {"US": "Estados Unidos", "ES": "España"}

_NEGOTIATED_RATE_RE = re.compile(
    r"(?:tarifas?|precios?|costes?|costos?)\s+"
    r"(?:negociad[oa]s?|acordad[oa]s?|intern[oa]s?|real(?:es)?)"
    r"|(?:acuerdo|contrato|condiciones)\s+(?:comercial(?:es)?\s+)?"
    r"(?:con|de)\s+(?:ups|fedex|dhl|mrw|seur)"
    r"|coste\s+por\s+kg|margen\s+(?:de|del|interno)"
    r"|descuento\s+(?:acordado|secreto|interno)",
    re.IGNORECASE,
)

_STREET_WORD = (
    r"(?:calle|carrer|avenida|avda\.?|plaza|paseo|"
    r"street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|highway|hwy\.?)"
)
_ADDRESS_RE = re.compile(
    rf"\b{_STREET_WORD}\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]",
    re.IGNORECASE,
)
_ADDRESS_NUMBER_RE = re.compile(
    r"\b\d{1,5}\s+(?:[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+\s+){1,3}"
    r"(?:street|st|avenue|ave|road|rd|calle|carrer|avenida)\b",
    re.IGNORECASE,
)
_POSTAL_RE = re.compile(
    r"\b(?:cp|c\.p\.|codigo postal|código postal|zip)\s*[:#]?\s*\d{4,5}\b",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r"\b(?:piso|puerta|portal|escalera|apartamento|apto\.?|suite|unit|floor)"
    r"\s*\d+\b",
    re.IGNORECASE,
)
_COORDINATES_RE = re.compile(
    r"\b-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}\b"
)
_WAREHOUSE_ROUTE_RE = re.compile(
    r"\b(?:ruta interna|rutas internas|pasillo|pasillos|estanteria|estantería|"
    r"estanterias|estanterías|rack|racks|ubicacion interna|ubicación interna|"
    r"layout del almacen|layout del almacén|puerta de carga|muelle de carga|"
    r"acceso de operarios|zona restringida|nave\s+\d+|"
    r"poligono|polígono|parque empresarial|edificio\s+\d+)\b",
    re.IGNORECASE,
)

_CREDENTIAL_RE = re.compile(
    r"\b(?:password|contrasena|contraseña|api[\s_-]?key|apikey|secret|"
    r"bearer|credencial|credenciales)\b"
    r"|\b(?:access|api|auth)\s+token\b|\btoken\s+de\s+(?:acceso|api)\b"
    r"|\beyJ[A-Za-z0-9_-]{10,}\b|\bsk-[A-Za-z0-9]{10,}\b",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}"
)

_INTERNAL_JSON_RE = re.compile(
    r'"(?:respuesta|propuesta_memoria|memory_proposal|cita_origen)"\s*:'
)

_PROMPT_LEAK_MARKERS = (
    "eres el agente de atencion al cliente de primera linea de trackflow",
    "jerarquia de instrucciones",
    "datos que nunca debes revelar",
    "reglas por pais",
    "reglas de memoria",
    "esquema de salida",
)

_STATUS_WORDS_RE = re.compile(
    r"\b(?:entregad[oa]s?|en\s+transito|en\s+tránsito|retrasad[oa]s?|"
    r"devuelt[oa]s?|perdid[oa]s?|firmad[oa]s?|repartid[oa]s?|"
    r"listo\s+para\s+enviar|pendiente\s+de\s+entrega)\b",
    re.IGNORECASE,
)

_SPAIN_POLICY_RE = re.compile(
    r"(?:politica|política|sla|devolucion(?:es)?|devolución(?:es)?|plazo)"
    r".{0,60}(?:espana|españa|espanol|español|espanola|española)"
    r"|(?:espana|españa|espanol|español|espanola|española).{0,60}"
    r"(?:politica|política|sla|devolucion(?:es)?|devolución(?:es)?|plazo)",
    re.IGNORECASE,
)
_US_POLICY_RE = re.compile(
    r"(?:politica|política|sla|devolucion(?:es)?|devolución(?:es)?|plazo)"
    r".{0,60}(?:estados\s+unidos|ee\.?\s*uu\.?|usa|estadounidense)"
    r"|(?:estados\s+unidos|ee\.?\s*uu\.?|usa|estadounidense).{0,60}"
    r"(?:politica|política|sla|devolucion(?:es)?|devolución(?:es)?|plazo)",
    re.IGNORECASE,
)
_ASSERTS_POLICY_RE = re.compile(
    r"\b(?:aplica|aplicar|segun|según|conforme|de\s+acuerdo\s+con|"
    r"corresponde|rige)\b",
    re.IGNORECASE,
)
_NEGATES_POLICY_RE = re.compile(
    r"\b(?:no\s+aplica|no\s+corresponde|no\s+puedo\s+aplicar|"
    r"no\s+se\s+aplica|no\s+rige|no\s+es\s+aplicable)\b",
    re.IGNORECASE,
)

_SAFE_REFUSAL_MARKERS = (
    "no puedo consultar el estado de pedidos",
    "no puedo cambiar mis instrucciones",
    "no puedo ayudarte con eso",
    "fuera de mi ambito",
    "no puedo mostrar esa informacion",
    "no puedo verificar la autorizacion",
)


@dataclass(frozen=True)
class OutputDecision:
    action: Literal["allow", "blocked"]
    answer: str
    guard: str | None = None
    category: str | None = None
    reason: str | None = None
    event: GuardrailEvent | None = None


def _looks_like_safe_refusal(answer: str) -> bool:
    normalized = normalize_text(answer)
    return any(marker in normalized for marker in _SAFE_REFUSAL_MARKERS)


def _prompt_leak(answer: str) -> bool:
    normalized = normalize_text(answer)
    if any(marker in normalized for marker in _PROMPT_LEAK_MARKERS):
        return True
    # Copia literal de una línea sustantiva del system prompt.
    for line in CX_SYSTEM_PROMPT.splitlines():
        candidate = normalize_text(line)
        if len(candidate) >= 55 and candidate in normalized:
            return True
    return False


def _asserts_wrong_policy(answer: str, *, required_country: str) -> bool:
    wrong_re = _SPAIN_POLICY_RE if required_country == "US" else _US_POLICY_RE
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer or ""):
        if not wrong_re.search(sentence):
            continue
        if not _ASSERTS_POLICY_RE.search(sentence):
            continue
        if _NEGATES_POLICY_RE.search(sentence):
            continue
        return True
    return False


def _blocked(
    *,
    answer: str,
    guard: str,
    category: str,
    reason: str,
    replacement: str,
    run_id: str | None,
    session_id: str | None,
    question: str | None,
    log: bool,
) -> OutputDecision:
    event = GuardrailEvent(
        guard=guard,
        category=category,
        action=ACTION_BLOCKED,
        reason=reason,
        run_id=run_id,
        session_id=session_id,
        snippet=safe_snippet(answer, limit=200),
        question_sha256=question_hash(question) if question else None,
    )
    if log:
        metrics.record(event)
    return OutputDecision(
        action="blocked",
        answer=replacement,
        guard=guard,
        category=category,
        reason=reason,
        event=event,
    )


def validate_output(
    answer: str,
    *,
    required_country: str | None = None,
    authorized_order_refs: tuple[str, ...] | list[str] = (),
    run_id: str | None = None,
    session_id: str | None = None,
    question: str | None = None,
    log: bool = True,
) -> OutputDecision:
    """Valida la respuesta final; devuelve una versión segura si falla."""

    text = str(answer or "").strip()
    if not text:
        return _blocked(
            answer="",
            guard="output_guard",
            category=CATEGORY_STRUCTURAL,
            reason="empty_answer",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    if len(text) > MAX_ANSWER_CHARS:
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_STRUCTURAL,
            reason="answer_too_long",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text) or "```" in text:
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_STRUCTURAL,
            reason="invalid_format",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    if _prompt_leak(text):
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_SECURITY,
            reason="prompt_leak",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    if _INTERNAL_JSON_RE.search(text):
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_CONTENT,
            reason="internal_format",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    if _CREDENTIAL_RE.search(text):
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_SECURITY,
            reason="credentials",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    if _NEGOTIATED_RATE_RE.search(text):
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_CONTENT,
            reason="negotiated_rate",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    if (
        _ADDRESS_RE.search(text)
        or _ADDRESS_NUMBER_RE.search(text)
        or _POSTAL_RE.search(text)
        or _UNIT_RE.search(text)
        or _COORDINATES_RE.search(text)
        or _WAREHOUSE_ROUTE_RE.search(text)
    ):
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_CONTENT,
            reason="warehouse_location",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    if _EMAIL_RE.search(text):
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_CONTENT,
            reason="personal_data_email",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    phone = _PHONE_RE.search(text)
    if (
        phone
        and len(re.sub(r"\D", "", phone.group(0))) >= 9
        and re.search(r"[+\s()\-]", phone.group(0))
    ):
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_CONTENT,
            reason="personal_data_phone",
            replacement=SAFE_OUTPUT_MESSAGE,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    if required_country in COUNTRY_LABELS and _asserts_wrong_policy(
        text, required_country=required_country
    ):
        label = COUNTRY_LABELS[required_country]
        replacement = (
            f"El pedido pertenece a {label}. Aplica la política de {label}; no "
            f"puedo aplicar la del otro país. Si quieres, revisamos la política "
            f"de {label}.\n\n{REDIRECT_LINE}"
        )
        return _blocked(
            answer=text,
            guard="output_guard",
            category=CATEGORY_CONTENT,
            reason="policy_mismatch",
            replacement=replacement,
            run_id=run_id,
            session_id=session_id,
            question=question,
            log=log,
        )

    mentioned = extract_order_refs(text)
    if mentioned and not _looks_like_safe_refusal(text):
        allowed = {ref.upper() for ref in authorized_order_refs}
        foreign = [ref for ref in mentioned if ref not in allowed]
        if foreign and _STATUS_WORDS_RE.search(text):
            return _blocked(
                answer=text,
                guard="order_authorization_guard",
                category=CATEGORY_SECURITY,
                reason="foreign_order_status",
                replacement=(
                    "No puedo consultar el estado de pedidos que no estén "
                    "asociados a tu sesión. Si el pedido es tuyo, puedo "
                    f"ayudarte con la devolución o con una incidencia.\n\n"
                    f"{REDIRECT_LINE}"
                ),
                run_id=run_id,
                session_id=session_id,
                question=question,
                log=log,
            )

    return OutputDecision(action="allow", answer=text)


__all__ = [
    "MAX_ANSWER_CHARS",
    "OutputDecision",
    "SAFE_OUTPUT_MESSAGE",
    "validate_output",
]
