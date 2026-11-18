"""Detección y resolución determinista de los conflictos del BRIEFING §7.

Los conflictos se detectan sobre estado estructurado (``draft_payload`` y el
resultado del evaluador de cumplimiento), nunca por consenso libre de LLMs.
El árbitro es siempre la persona o la regla fija del briefing.
"""

from __future__ import annotations

import copy
from typing import Final

from data.pipelines.rfp_proposal.evaluators.compliance import evaluate_compliance
from data.pipelines.rfp_proposal.policy import (
    RETURNS_MIN_HOURS,
    RULE_CURRENCY_BY_COUNTRY,
    RULE_RETURNS_MIN_48H,
)
from data.pipelines.rfp_proposal.render import render_section

from .contracts import fallback_brief
from .trace import utc_now

TRIGGER_VOLUME_CAPACITY: Final[str] = "volume-vs-capacity"
TRIGGER_RETURNS_SLA: Final[str] = "returns-sla-breach"
TRIGGER_CURRENCY: Final[str] = "currency-mismatch"

ARBITRATOR_MIGUEL: Final[str] = "Miguel Torres"
ARBITRATOR_SOFIA: Final[str] = "Sofía Ramos"

ARBITRATOR_BY_TRIGGER: Final[dict[str, str]] = {
    TRIGGER_VOLUME_CAPACITY: ARBITRATOR_MIGUEL,
    TRIGGER_RETURNS_SLA: ARBITRATOR_SOFIA,
    TRIGGER_CURRENCY: ARBITRATOR_MIGUEL,
}

RULE_BY_TRIGGER: Final[dict[str, str]] = {
    TRIGGER_VOLUME_CAPACITY: (
        "Limitar el volumen de la propuesta a la capacidad comprometida de "
        "warehouse; Last Mile revisa volumen y coste a la baja."
    ),
    TRIGGER_RETURNS_SLA: (
        "Forzar request_changes en toda sección que prometa devoluciones en "
        "menos de 48 horas; no se genera documento final hasta cumplir."
    ),
    TRIGGER_CURRENCY: (
        "Reescribir las secciones ofensoras a la moneda del país del cliente; "
        "se rechazan si no se resuelve tras el límite de rondas."
    ),
}


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _draft_for_evaluation(section: dict) -> dict:
    payload = dict(section.get("draft_payload") or {})
    payload["body_markdown"] = section.get("draft_content") or payload.get(
        "body_markdown", ""
    )
    payload.setdefault("currency", section.get("currency"))
    return payload


def capacity_signal(section: dict) -> float | None:
    capacity = (section.get("draft_payload") or {}).get("capacity") or {}
    for key in (
        "max_monthly_orders",
        "monthly_orders_capacity",
        "throughput_orders_month",
    ):
        value = _number(capacity.get(key))
        if value is not None:
            return value
    return None


def volume_signal(section: dict, *, facts: dict | None = None) -> float | None:
    payload = section.get("draft_payload") or {}
    volume = payload.get("volume") or {}
    for key in ("monthly_orders", "assumed_monthly_orders", "monthly_volume"):
        value = _number(volume.get(key))
        if value is not None:
            return value
    value = _number((facts or {}).get("monthly_volume"))
    return value


def _section_compliance(
    section: dict,
    *,
    briefs: dict[str, dict],
    proposal: dict,
    intake: dict,
) -> dict:
    department_id = section.get("department_id") or ""
    brief = briefs.get(department_id) or fallback_brief(
        section, proposal=proposal, intake=intake
    )
    return evaluate_compliance(brief, _draft_for_evaluation(section))


def _violations_with_rule(evaluation: dict, rule_id: str) -> list[dict]:
    compliance = (evaluation or {}).get("compliance") or {}
    return [
        violation
        for violation in compliance.get("violations") or []
        if isinstance(violation, dict) and violation.get("rule_id") == rule_id
    ]


def _conflict(
    *,
    trigger_id: str,
    affected_sections: list[str],
    evidence: dict,
    arbitrator: str | None = None,
) -> dict:
    return {
        "trigger_id": trigger_id,
        "arbitrator": arbitrator or ARBITRATOR_BY_TRIGGER[trigger_id],
        "rule": RULE_BY_TRIGGER[trigger_id],
        "affected_sections": affected_sections,
        "evidence": evidence,
        "detected_at": utc_now(),
    }


def detect_conflicts(
    sections: dict[str, dict],
    *,
    briefs: dict[str, dict] | None = None,
    proposal: dict,
    intake: dict | None,
    currency: str | None,
) -> list[dict]:
    """Devuelve los conflictos detectables en el estado estructurado."""

    briefs = briefs or {}
    intake = intake or {}
    conflicts: list[dict] = []

    currency_offenders: list[str] = []
    returns_offenders: list[str] = []
    evidence_currency: dict[str, list] = {}
    evidence_returns: dict[str, list] = {}

    for department_id, section in sections.items():
        section = {**section, "currency": section.get("currency") or currency}
        structured_currency = _text(
            (section.get("draft_payload") or {}).get("currency")
        )
        pricing_currencies = {
            _text(row.get("currency"))
            for row in (section.get("draft_payload") or {}).get("pricing") or []
            if isinstance(row, dict) and row.get("currency")
        }
        evaluation = _section_compliance(
            section, briefs=briefs, proposal=proposal, intake=intake
        )
        currency_violations = _violations_with_rule(
            evaluation, RULE_CURRENCY_BY_COUNTRY
        )
        returns_violations = _violations_with_rule(
            evaluation, RULE_RETURNS_MIN_48H
        )
        mismatch = bool(
            currency
            and (
                (structured_currency and structured_currency.upper() != currency.upper())
                or any(
                    value.upper() != currency.upper()
                    for value in pricing_currencies
                    if value
                )
                or currency_violations
            )
        )
        if mismatch:
            currency_offenders.append(department_id)
            evidence_currency[department_id] = {
                "currency": structured_currency or currency,
                "pricing_currencies": sorted(pricing_currencies),
                "violations": currency_violations,
            }

        turnaround = (section.get("draft_payload") or {}).get("turnaround") or {}
        structured_hours = [
            _number(turnaround.get("minimum_hours")),
            _number(turnaround.get("committed_hours")),
        ]
        if returns_violations or any(
            value is not None and value < RETURNS_MIN_HOURS
            for value in structured_hours
        ):
            returns_offenders.append(department_id)
            evidence_returns[department_id] = {
                "turnaround": turnaround,
                "violations": returns_violations,
            }

    if currency_offenders:
        conflicts.append(
            _conflict(
                trigger_id=TRIGGER_CURRENCY,
                affected_sections=currency_offenders,
                evidence={
                    "expected_currency": currency,
                    "sections": evidence_currency,
                },
            )
        )

    if returns_offenders:
        primary = (
            ARBITRATOR_SOFIA
            if set(returns_offenders) <= {"reverse"}
            else ARBITRATOR_MIGUEL
        )
        conflicts.append(
            _conflict(
                trigger_id=TRIGGER_RETURNS_SLA,
                affected_sections=returns_offenders,
                evidence={
                    "minimum_hours": RETURNS_MIN_HOURS,
                    "sections": evidence_returns,
                },
                arbitrator=primary,
            )
        )

    if "warehouse" in sections and "lastmile" in sections:
        capacity = capacity_signal(sections["warehouse"])
        volume = volume_signal(sections["lastmile"], facts=intake.get("facts"))
        if capacity is not None and volume is not None and volume > capacity:
            conflicts.append(
                _conflict(
                    trigger_id=TRIGGER_VOLUME_CAPACITY,
                    affected_sections=["warehouse", "lastmile"],
                    evidence={
                        "warehouse_capacity_orders": capacity,
                        "lastmile_assumed_orders": volume,
                        "excess_orders": volume - capacity,
                    },
                )
            )

    return conflicts


def _replace_currency_tokens(value: str, expected: str) -> str:
    replacements = {
        "USD": expected,
        "EUR": expected,
        "US$": expected,
        "$": expected if expected == "USD" else "€",
        "€": expected if expected == "EUR" else "$",
    }
    result = value
    for token, replacement in replacements.items():
        result = result.replace(token, replacement)
    return result


def rewrite_section_currency(section: dict, expected: str) -> dict:
    """Reescribe moneda en el estado estructurado y re-renderiza el Markdown."""

    updated = copy.deepcopy(section)
    payload = dict(updated.get("draft_payload") or {})
    payload["currency"] = expected
    for row in payload.get("pricing") or []:
        if isinstance(row, dict):
            row["currency"] = expected
    for field in ("executive_summary",):
        if isinstance(payload.get(field), str):
            payload[field] = _replace_currency_tokens(payload[field], expected)
    for field in ("assumptions", "open_questions", "additional_open_questions"):
        values = payload.get(field)
        if isinstance(values, list):
            payload[field] = [
                _replace_currency_tokens(item, expected)
                if isinstance(item, str)
                else item
                for item in values
            ]
    for offering in payload.get("offerings") or []:
        if isinstance(offering, dict):
            for key in ("name", "detail"):
                if isinstance(offering.get(key), str):
                    offering[key] = _replace_currency_tokens(
                        offering[key], expected
                    )
    assumption = (
        f"Moneda ajustada a {expected} por arbitraje de Miguel Torres "
        "(BRIEFING §5.1)."
    )
    assumptions = list(payload.get("assumptions") or [])
    if assumption not in assumptions:
        assumptions.append(assumption)
    payload["assumptions"] = assumptions
    updated["draft_payload"] = payload
    updated["draft_content"] = render_section(payload)
    return updated


def cap_section_volume(section: dict, capacity: float) -> dict:
    """Aplica el límite de volumen resuelto por el árbitro."""

    updated = copy.deepcopy(section)
    payload = dict(updated.get("draft_payload") or {})
    volume = dict(payload.get("volume") or {})
    volume["monthly_orders"] = int(capacity)
    volume["capped_by"] = ARBITRATOR_MIGUEL
    payload["volume"] = volume
    assumption = (
        f"Volumen limitado a {int(capacity)} pedidos/mes por la capacidad "
        "comprometida de Warehouse Operations (arbitraje de Miguel Torres)."
    )
    assumptions = list(payload.get("assumptions") or [])
    if assumption not in assumptions:
        assumptions.append(assumption)
    payload["assumptions"] = assumptions
    updated["draft_payload"] = payload
    updated["draft_content"] = render_section(payload)
    return updated


def regeneration_feedback(conflict: dict, department_id: str) -> str:
    """Feedback determinista para el generador de la Parte 2."""

    trigger = conflict.get("trigger_id")
    if trigger == TRIGGER_RETURNS_SLA:
        return (
            "El briefing §5 prohíbe prometer devoluciones en menos de "
            f"{RETURNS_MIN_HOURS} horas. Elimina cualquier plazo inferior y "
            "deja el tiempo comprometido en 48 horas o pendiente de confirmar."
        )
    if trigger == TRIGGER_CURRENCY:
        return (
            "La sección debe cotizar en la moneda del país del cliente "
            f"({conflict.get('evidence', {}).get('expected_currency')}). "
            "Corrige tarifas y texto; no mezcles monedas."
        )
    if trigger == TRIGGER_VOLUME_CAPACITY:
        if department_id == "warehouse":
            return (
                "Declara la capacidad mensual comprometida (pedidos/mes) que "
                "puede soportar Warehouse Operations; no inventes la cifra."
            )
        return (
            "Ajusta el volumen asumido a la capacidad comprometida por "
            "Warehouse Operations y revisa el coste por envío a la baja."
        )
    return "Revisa la sección conforme al briefing de TrackFlow."


__all__ = [
    "ARBITRATOR_BY_TRIGGER",
    "ARBITRATOR_MIGUEL",
    "ARBITRATOR_SOFIA",
    "RULE_BY_TRIGGER",
    "TRIGGER_CURRENCY",
    "TRIGGER_RETURNS_SLA",
    "TRIGGER_VOLUME_CAPACITY",
    "cap_section_volume",
    "capacity_signal",
    "detect_conflicts",
    "draft_for_evaluation",
    "regeneration_feedback",
    "rewrite_section_currency",
    "violations_with_rule",
    "volume_signal",
]

# Alias públicos para el gate de cierre.
draft_for_evaluation = _draft_for_evaluation
violations_with_rule = _violations_with_rule
