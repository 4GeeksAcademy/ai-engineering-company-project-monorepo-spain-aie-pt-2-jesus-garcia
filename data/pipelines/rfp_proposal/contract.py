"""Contrato de entrada de la Parte 2: el handoff de enrutamiento de la Parte 1.

La Parte 2 **no reparsea el PDF**. Recibe ``ticket_id`` + el payload del
synthesizer persistido en PostgreSQL (``rfp_ticket.handoff_payload``) y valida
su forma antes de generar ninguna sección.
"""

from __future__ import annotations

import json
from typing import Final

from data.pipelines.rfp_intake.catalog import (
    DEPARTMENTS,
    normalize_country,
)
from data.pipelines.rfp_intake.worker import numeric_tokens

from .policy import expected_currency

SUPPORTED_CONTRACT_VERSIONS: Final[frozenset[str]] = frozenset(
    {"rfp-intake-v1", "rfp-intake-v1.1"}
)
REQUIRED_STATUS: Final[str] = "analisis_completo"
FACT_FIELDS: Final[tuple[str, ...]] = (
    "monthly_volume",
    "sku_count",
    "return_volume",
    "return_rate",
    "deadline",
    "budget_range",
)


class HandoffContractError(ValueError):
    """El payload persistido no cumple el contrato de la Parte 1."""


def _clean_key_aspects(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    aspects: list[dict] = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("aspect"), str):
            aspects.append(
                {
                    "aspect": item["aspect"].strip(),
                    "detail": str(item.get("detail") or "").strip(),
                    "evidence": str(item.get("evidence") or "").strip(),
                    "confidence": str(item.get("confidence") or "medium"),
                }
            )
        elif isinstance(item, str) and item.strip():
            aspects.append(
                {
                    "aspect": item.strip(),
                    "detail": item.strip(),
                    "evidence": "",
                    "confidence": "medium",
                }
            )
    return aspects


def _clean_questions(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _clean_facts(value: object) -> dict:
    facts = {field: None for field in FACT_FIELDS}
    if isinstance(value, dict):
        for field in FACT_FIELDS:
            facts[field] = value.get(field)
    return facts


def parse_intake_handoff(
    payload: dict | None,
    *,
    ticket_id: str | None = None,
    fallback_facts: dict | None = None,
) -> dict:
    """Valida y normaliza el handoff. Lanza ``HandoffContractError`` si no sirve."""

    if not isinstance(payload, dict) or not payload:
        raise HandoffContractError(
            "El ticket no tiene handoff de la Parte 1 (handoff_payload vacío)."
        )

    version = payload.get("contract_version")
    if version not in SUPPORTED_CONTRACT_VERSIONS:
        raise HandoffContractError(
            f"Contrato de handoff no soportado: {version!r}. "
            f"Versiones válidas: {sorted(SUPPORTED_CONTRACT_VERSIONS)}."
        )

    status = payload.get("status")
    if status != REQUIRED_STATUS:
        raise HandoffContractError(
            "El handoff no está en análisis completo "
            f"(status={status!r}); la Parte 1 todavía no lo marcó listo."
        )

    handoff_ticket = payload.get("ticket_id")
    if ticket_id and handoff_ticket and handoff_ticket != ticket_id:
        raise HandoffContractError(
            "El handoff pertenece a otro ticket: "
            f"{handoff_ticket} != {ticket_id}."
        )

    client = payload.get("client") or {}
    if not isinstance(client, dict):
        raise HandoffContractError("El campo `client` del handoff no es un objeto.")

    client_country = normalize_country(client.get("country"))
    currency = payload.get("currency") or client.get("currency")
    if not currency:
        currency = expected_currency(client_country)
    if not currency:
        raise HandoffContractError(
            "El handoff no determina la moneda (client_country/currency)."
        )

    raw_departments = payload.get("departments")
    if not isinstance(raw_departments, list) or not raw_departments:
        raise HandoffContractError(
            "El handoff no incluye departamentos activos: no hay secciones que generar."
        )

    departments: list[dict] = []
    seen: set[str] = set()
    for item in raw_departments:
        if not isinstance(item, dict):
            continue
        department_id = item.get("department_id")
        if department_id not in DEPARTMENTS:
            raise HandoffContractError(
                f"Departamento fuera del catálogo cerrado: {department_id!r}."
            )
        if department_id in seen:
            raise HandoffContractError(
                f"Departamento duplicado en el handoff: {department_id}."
            )
        seen.add(department_id)
        spec = DEPARTMENTS[department_id]
        departments.append(
            {
                "department_id": department_id,
                "department_label": item.get("department_label") or spec["label"],
                "responsible": item.get("responsible") or spec["responsible"],
                "focus": str(item.get("focus") or "").strip(),
                "key_aspects": _clean_key_aspects(item.get("key_aspects")),
                "open_questions": _clean_questions(item.get("open_questions")),
            }
        )

    if not departments:
        raise HandoffContractError(
            "El handoff no incluye ningún departamento válido del catálogo."
        )

    facts = _clean_facts(payload.get("rfp_facts"))
    if fallback_facts:
        for field in FACT_FIELDS:
            if facts.get(field) is None and fallback_facts.get(field) is not None:
                facts[field] = fallback_facts.get(field)

    return {
        "contract_version": version,
        "ticket_id": handoff_ticket or ticket_id,
        "rfp_id": payload.get("rfp_id"),
        "client": {
            "name": client.get("name"),
            "country": client_country,
            "currency": currency,
            "contact": client.get("contact") or {},
        },
        "client_country": client_country,
        "currency": currency,
        "services_requested": list(payload.get("services_requested") or []),
        "unknown_services": list(payload.get("unknown_services") or []),
        "facts": facts,
        "departments": departments,
        "questions_to_ask": _clean_questions(payload.get("questions_to_ask")),
        "conflicts": list(payload.get("conflicts") or []),
        "sales_summary": str(payload.get("sales_summary") or ""),
        "source": payload.get("source") or {},
    }


def section_brief(handoff: dict, department: dict) -> dict:
    """Slice mínimo que recibe un generador/evaluador de esa sección.

    Incluye solo su departamento y los datos compartidos imprescindibles
    (país, moneda, volumen, deadline). Nunca el documento completo ni otras
    secciones.
    """

    return {
        "ticket_id": handoff["ticket_id"],
        "rfp_id": handoff.get("rfp_id"),
        "client": handoff["client"],
        "client_country": handoff["client_country"],
        "currency": handoff["currency"],
        "services_requested": handoff["services_requested"],
        "facts": handoff["facts"],
        "department_id": department["department_id"],
        "department_label": department["department_label"],
        "responsible": department["responsible"],
        "focus": department["focus"],
        "key_aspects": department["key_aspects"],
        "open_questions": department["open_questions"],
        "questions_to_ask": [
            question
            for question in handoff.get("questions_to_ask") or []
            if question.get("department_id") == department["department_id"]
        ],
        "conflicts": [
            conflict
            for conflict in handoff.get("conflicts") or []
            if conflict.get("department_id") == department["department_id"]
        ],
    }


def brief_numbers(brief: dict) -> set[str]:
    """Cifras trazables a la RFP y al handoff para el guardarraíl numérico."""

    source = json.dumps(
        {
            "facts": brief.get("facts"),
            "key_aspects": brief.get("key_aspects"),
            "open_questions": brief.get("open_questions"),
            "client": brief.get("client"),
        },
        ensure_ascii=False,
    )
    return numeric_tokens(source)


def briefs_for_handoff(handoff: dict) -> list[dict]:
    return [
        section_brief(handoff, department)
        for department in handoff["departments"]
    ]
