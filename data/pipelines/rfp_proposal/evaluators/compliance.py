"""Evaluador de cumplimiento de las reglas del briefing.

Es un motor de reglas determinista: no delega el juicio al LLM. Cada
``violation`` cita la regla (``rule_id``), el fragmento infractor y el cambio
exigido, que es justo lo que recibe el generador en el reintento.
"""

from __future__ import annotations

import json
import re
from typing import Final

from data.pipelines.rfp_intake.catalog import normalize_text
from data.pipelines.rfp_intake.worker import numeric_tokens

from ..contract import brief_numbers
from ..policy import (
    DEPARTMENT_REQUIRED_BLOCKS,
    RETURNS_MIN_HOURS,
    RULE_CARRIER_RATES_CONFIDENTIAL,
    RULE_CURRENCY_BY_COUNTRY,
    RULE_DELIVERY_SLA,
    RULE_NO_INVENTED_FIGURES,
    RULE_RETURNS_MIN_48H,
    RULE_VOLUME_DISCOUNTS,
    SLA_ON_TIME_PCT,
    format_rule_id,
    policy_numbers,
)
from ..rate_card import rate_card_numbers

CARRIER_NAMES: Final[tuple[str, ...]] = ("UPS", "FedEx", "DHL", "MRW", "SEUR")
FORBIDDEN_PHRASES: Final[tuple[str, ...]] = (
    "tarifa negociada",
    "tarifas negociadas",
    "tarifa con el transportista",
    "tarifa de transportista",
    "coste interno",
    "margen",
)
CURRENCY_TOKENS: Final[dict[str, str]] = {
    "USD": "USD",
    "US$": "USD",
    "$": "USD",
    "EUR": "EUR",
    "€": "EUR",
    "GBP": "GBP",
    "£": "GBP",
    "MXN": "MXN",
}
MANDATORY_PRICING_CONCEPT: Final[dict[str, str]] = {
    "warehouse": "almacen",
    "lastmile": "env",
    "reverse": "devoluc",
}

_MONEY_RE = re.compile(
    r"(\d[\d.,]*)\s*(USD|EUR|US\$|\$|€|£|GBP|MXN)", re.IGNORECASE
)
_CURRENCY_RE = re.compile(r"\b(USD|EUR|GBP|MXN)\b|(\$|€|£)")
_RETURNS_CONTEXT_RE = re.compile(
    r"devoluc|return|reacondicion|reembolso|retorno", re.IGNORECASE
)
_HOURS_RE = re.compile(r"(\d{1,3})\s*(?:h\b|hrs?\b|horas?\b|hours?\b)", re.IGNORECASE)
_DAYS_RE = re.compile(r"(\d{1,2})\s*(?:d[ií]as?\b|days?\b)", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _violation(
    rule_id: str,
    message: str,
    *,
    excerpt: str = "",
    required_change: str = "",
) -> dict:
    return {
        "rule_id": rule_id,
        "message": message,
        "excerpt": excerpt[:300],
        "required_change": required_change,
    }


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text or "") if part.strip()]


def _currency_name(token: str) -> str:
    return CURRENCY_TOKENS.get(token.upper(), CURRENCY_TOKENS.get(token, token.upper()))


# --- reglas ------------------------------------------------------------------


def _check_currency(brief: dict, draft: dict) -> list[dict]:
    expected = brief.get("currency")
    if not expected:
        return [
            _violation(
                RULE_CURRENCY_BY_COUNTRY,
                "La sección no tiene una moneda canónica determinada.",
                required_change="Confirmar el país del cliente antes de cotizar.",
            )
        ]
    violations: list[dict] = []
    for row in draft.get("pricing") or []:
        amount = row.get("amount")
        currency = row.get("currency")
        if amount is None or not currency:
            continue
        if str(currency).upper() != expected:
            violations.append(
                _violation(
                    RULE_CURRENCY_BY_COUNTRY,
                    f"La tarifa de '{row.get('concept')}' está en {currency} "
                    f"y el cliente opera en {expected}.",
                    excerpt=f"{row.get('concept')}: {amount} {currency}",
                    required_change=f"Reescribir la cifra en {expected}.",
                )
            )
    body = draft.get("body_markdown") or ""
    for sentence in _sentences(body):
        for match in _CURRENCY_RE.finditer(sentence):
            token = match.group(0)
            currency = _currency_name(token)
            if currency and currency != expected:
                violations.append(
                    _violation(
                        RULE_CURRENCY_BY_COUNTRY,
                        f"La sección menciona {currency} cuando la moneda "
                        f"canónica es {expected}.",
                        excerpt=sentence,
                        required_change=f"Usar solo {expected} en toda la sección.",
                    )
                )
    return violations


def _check_sla(draft: dict) -> list[dict]:
    sla = draft.get("sla") or {}
    value = sla.get("on_time_pct")
    if not isinstance(value, (int, float)):
        return [
            _violation(
                RULE_DELIVERY_SLA,
                "La sección no indica el SLA de entrega a tiempo (%) comprometido.",
                required_change=f"Añadir el compromiso de {SLA_ON_TIME_PCT:g}%.",
            )
        ]
    if float(value) != SLA_ON_TIME_PCT:
        return [
            _violation(
                RULE_DELIVERY_SLA,
                f"La sección promete un SLA de {value}% y TrackFlow se "
                f"compromete a {SLA_ON_TIME_PCT:g}% mensual por país.",
                excerpt=f"SLA: {value}%",
                required_change=f"Ajustar el SLA a {SLA_ON_TIME_PCT:g}%.",
            )
        ]
    return []


def _returns_text_violations(body: str) -> list[dict]:
    violations: list[dict] = []
    for sentence in _sentences(body):
        if not _RETURNS_CONTEXT_RE.search(sentence):
            continue
        for match in _HOURS_RE.finditer(sentence):
            hours = int(match.group(1))
            if hours < RETURNS_MIN_HOURS:
                violations.append(
                    _violation(
                        RULE_RETURNS_MIN_48H,
                        f"La sección promete procesar devoluciones en {hours} "
                        f"horas; el mínimo permitido es {RETURNS_MIN_HOURS}.",
                        excerpt=sentence,
                        required_change=(
                            f"Fijar el procesamiento en {RETURNS_MIN_HOURS} horas "
                            "o más y eliminar el plazo inferior."
                        ),
                    )
                )
        for match in _DAYS_RE.finditer(sentence):
            days = int(match.group(1))
            if days * 24 < RETURNS_MIN_HOURS:
                violations.append(
                    _violation(
                        RULE_RETURNS_MIN_48H,
                        f"La sección promete procesar devoluciones en {days} "
                        f"día(s); el mínimo permitido es {RETURNS_MIN_HOURS} horas.",
                        excerpt=sentence,
                        required_change=(
                            f"Fijar el procesamiento en {RETURNS_MIN_HOURS} horas "
                            "o más."
                        ),
                    )
                )
    return violations


def _check_returns(draft: dict) -> list[dict]:
    violations: list[dict] = []
    turnaround = draft.get("turnaround") or {}
    for field, label in (
        ("minimum_hours", "compromiso mínimo"),
        ("committed_hours", "tiempo comprometido"),
    ):
        value = turnaround.get(field)
        if isinstance(value, (int, float)) and float(value) < RETURNS_MIN_HOURS:
            violations.append(
                _violation(
                    RULE_RETURNS_MIN_48H,
                    f"El {label} de devoluciones es de {value} horas; el "
                    f"mínimo permitido es {RETURNS_MIN_HOURS}.",
                    excerpt=f"{field}={value}",
                    required_change=f"Elevar el {label} a {RETURNS_MIN_HOURS} h o más.",
                )
            )
    violations.extend(_returns_text_violations(draft.get("body_markdown") or ""))
    return violations


def _check_discounts(draft: dict) -> list[dict]:
    tiers = draft.get("discount_tiers")
    if not isinstance(tiers, list) or len(tiers) < 2:
        return [
            _violation(
                RULE_VOLUME_DISCOUNTS,
                "La sección no incluye una tabla de descuentos por volumen "
                "con al menos dos tramos.",
                required_change="Añadir la tabla de descuentos por volumen publicada.",
            )
        ]
    for tier in tiers:
        if not isinstance(tier, dict):
            return [
                _violation(
                    RULE_VOLUME_DISCOUNTS,
                    "La tabla de descuentos contiene un tramo inválido.",
                    required_change="Rehacer la tabla con volúmenes y porcentajes.",
                )
            ]
        discount = tier.get("discount_pct")
        minimum = tier.get("min_monthly_volume")
        if not isinstance(discount, (int, float)) or discount < 0 or discount > 50:
            return [
                _violation(
                    RULE_VOLUME_DISCOUNTS,
                    "Un tramo de descuento tiene un porcentaje fuera de rango.",
                    excerpt=json.dumps(tier, ensure_ascii=False),
                    required_change="Usar la tabla de descuentos publicada.",
                )
            ]
        if not isinstance(minimum, int) or minimum < 0:
            return [
                _violation(
                    RULE_VOLUME_DISCOUNTS,
                    "Un tramo de descuento no tiene volumen mínimo válido.",
                    excerpt=json.dumps(tier, ensure_ascii=False),
                    required_change="Usar la tabla de descuentos publicada.",
                )
            ]
    if "descuentos por volumen" not in (draft.get("body_markdown") or "").lower():
        return [
            _violation(
                RULE_VOLUME_DISCOUNTS,
                "La tabla de descuentos no aparece en el texto de la sección.",
                required_change="Renderizar la tabla de descuentos por volumen.",
            )
        ]
    return []


def _mentions_affirmatively(text: str, phrase: str) -> bool:
    """Ignora negaciones tipo 'no revelamos tarifas negociadas'."""

    lowered = (text or "").lower()
    start = 0
    while True:
        index = lowered.find(phrase, start)
        if index == -1:
            return False
        context = lowered[max(0, index - 40) : index]
        if not any(negation in context for negation in ("no ", "sin ", "nunca")):
            return True
        start = index + len(phrase)


def _check_carrier_rates(draft: dict) -> list[dict]:
    violations: list[dict] = []
    for row in draft.get("pricing") or []:
        concept = str(row.get("concept") or "")
        if row.get("amount") is not None and any(
            carrier.lower() in concept.lower() for carrier in CARRIER_NAMES
        ):
            violations.append(
                _violation(
                    RULE_CARRIER_RATES_CONFIDENTIAL,
                    "La sección publica un precio asociado a un transportista.",
                    excerpt=f"{concept}: {row.get('amount')} {row.get('currency')}",
                    required_change=(
                        "Eliminar la tarifa por transportista y ofrecer solo el "
                        "coste final al cliente."
                    ),
                )
            )
    for line in (draft.get("body_markdown") or "").splitlines():
        lowered = line.lower()
        has_carrier = any(carrier.lower() in lowered for carrier in CARRIER_NAMES)
        if has_carrier and _MONEY_RE.search(line):
            violations.append(
                _violation(
                    RULE_CARRIER_RATES_CONFIDENTIAL,
                    "La sección revela un importe junto al nombre de un transportista.",
                    excerpt=line.strip(),
                    required_change=(
                        "Quitar el importe de la línea del transportista; solo se "
                        "publica el coste final ofrecido al cliente."
                    ),
                )
            )
        for phrase in FORBIDDEN_PHRASES:
            if _mentions_affirmatively(lowered, phrase):
                violations.append(
                    _violation(
                        RULE_CARRIER_RATES_CONFIDENTIAL,
                        f"La sección menciona '{phrase}'.",
                        excerpt=line.strip(),
                        required_change=(
                            "Sustituirlo por el coste final ofrecido al cliente, "
                            "sin detalle de la tarifa negociada."
                        ),
                    )
                )
                break
    return violations


def _check_invented_figures(brief: dict, draft: dict) -> list[dict]:
    deterministic = {
        key: draft.get(key)
        for key in (
            "capacity",
            "onboarding",
            "carriers",
            "process",
            "turnaround",
            "pricing",
            "discount_tiers",
            "sla",
        )
    }
    allowed = (
        brief_numbers(brief)
        | policy_numbers()
        | rate_card_numbers()
        | numeric_tokens(json.dumps(deterministic, ensure_ascii=False))
    )
    body = draft.get("body_markdown") or ""
    invented = sorted(numeric_tokens(body) - allowed)
    if not invented:
        return []
    excerpt = ""
    for sentence in _sentences(body):
        if numeric_tokens(sentence) & set(invented):
            excerpt = sentence
            break
    return [
        _violation(
            RULE_NO_INVENTED_FIGURES,
            "La sección contiene cifras que no constan en la RFP, el handoff ni "
            f"la tarifa publicada: {', '.join(invented)}.",
            excerpt=excerpt,
            required_change=(
                "Eliminar esas cifras o declararlas como pendientes de "
                "confirmación con una pregunta abierta."
            ),
        )
    ]


def _check_format(department_id: str, draft: dict) -> list[dict]:
    rule_id = format_rule_id(department_id)
    violations: list[dict] = []
    for key, label in DEPARTMENT_REQUIRED_BLOCKS.get(department_id, ()):
        if not draft.get(key):
            violations.append(
                _violation(
                    rule_id,
                    f"Falta el bloque obligatorio de la sección: {label}.",
                    required_change=f"Añadir el bloque '{key}' ({label}).",
                )
            )
    concept = MANDATORY_PRICING_CONCEPT.get(department_id)
    if concept:
        rows = draft.get("pricing") or []
        expected = normalize_text(concept)
        if not any(expected in normalize_text(str(row.get("concept") or "")) for row in rows):
            violations.append(
                _violation(
                    rule_id,
                    f"La sección no cotiza el concepto obligatorio del "
                    f"departamento ({concept}).",
                    required_change=f"Añadir una fila de tarifa para '{concept}'.",
                )
            )
    return violations


def evaluate_compliance(brief: dict, draft: dict) -> dict:
    department_id = brief.get("department_id") or draft.get("department_id") or ""
    rule_ids = [
        RULE_CURRENCY_BY_COUNTRY,
        RULE_DELIVERY_SLA,
        RULE_RETURNS_MIN_48H,
        RULE_VOLUME_DISCOUNTS,
        RULE_CARRIER_RATES_CONFIDENTIAL,
        RULE_NO_INVENTED_FIGURES,
        format_rule_id(department_id),
    ]
    violations: list[dict] = []
    violations.extend(_check_currency(brief, draft))
    violations.extend(_check_sla(draft))
    violations.extend(_check_returns(draft))
    violations.extend(_check_discounts(draft))
    violations.extend(_check_carrier_rates(draft))
    violations.extend(_check_invented_figures(brief, draft))
    violations.extend(_check_format(department_id, draft))

    return {
        "pass": not violations,
        "rule_ids": rule_ids,
        "violations": violations,
    }
