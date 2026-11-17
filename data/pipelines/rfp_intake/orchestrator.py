"""Orquestador: descompone la RFP en workstreams por departamento.

La selección de departamentos es determinista a partir del catálogo. El LLM
solo puede enriquecer el foco de cada workstream dentro de los departamentos
ya activos; nunca puede añadir uno nuevo ni cambiar el alcance.
"""

from __future__ import annotations

import json
import logging
import re

from .catalog import (
    DEPARTMENT_KEYWORDS,
    DEPARTMENT_ORDER,
    DEPARTMENTS,
    departments_for_services,
    normalize_text,
)
from .llm import JsonLlm, LlmError

logger = logging.getLogger(__name__)

MAX_PLAN_INPUT_CHARS = 14_000
MAX_EXCERPT_CHARS = 6_000

SYSTEM_PROMPT = """Eres el orquestador de propuestas de TrackFlow. Recibes los metadatos de una RFP ya aceptada y la lista cerrada de departamentos que deben analizarla.

Tu tarea es preparar un workstream por departamento activo. No puedes añadir departamentos: solo puedes describir el foco y las palabras clave para localizar los extractos relevantes del documento.

Departamentos disponibles y responsables:
- warehouse (Warehouse Operations, Ana Whitfield): almacenamiento, capacidad, pallets, SKUs, onboarding.
- lastmile (Last Mile and Carrier Management, Carlos Vega): envíos, transportistas, destinos, SLA de entrega.
- reverse (Reverse Logistics, Sofía Ramos): devoluciones, inspección, reacondicionamiento, restock.

Devuelve EXCLUSIVAMENTE:
{
  "workstreams": [
    {
      "department_id": "warehouse" | "lastmile" | "reverse",
      "focus": "qué debe responder este departamento para la propuesta, en una frase",
      "excerpt_keywords": ["palabras o frases para localizar extractos relevantes"]
    }
  ]
}

Reglas:
1. Devuelve exactamente un workstream por cada departamento de la lista permitida.
2. No inventes cifras ni condiciones. No decidas precios.
3. Si un dato falta, el foco puede pedir confirmarlo como pregunta abierta.
4. No incluyas texto fuera del objeto JSON."""


def _split_blocks(markdown: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", markdown or "")
    return [block.strip() for block in blocks if block.strip()]


def _score_block(block: str, keywords: list[str]) -> int:
    haystack = normalize_text(block)
    return sum(1 for keyword in keywords if normalize_text(keyword) in haystack)


def select_excerpts(
    markdown: str,
    keywords: list[str],
    *,
    max_chars: int = MAX_EXCERPT_CHARS,
) -> list[str]:
    """Selecciona bloques relevantes sin recurrir a otro LLM.

    Se incluyen siempre el primer bloque y los bloques con datos compartidos
    (alcance, volumen, fechas, presupuesto); después los mejor puntuados por
    las keywords del departamento. Determinista y testeable.
    """

    blocks = _split_blocks(markdown)
    if not blocks:
        return []

    shared = (
        "services requested",
        "alcance",
        "scope of work",
        "volumen",
        "volume",
        "pedidos",
        "orders",
        "plazo",
        "deadline",
        "fecha",
        "presupuesto",
        "budget",
        "devoluciones",
        "returns",
    )
    scored: list[tuple[int, int, str]] = []
    for index, block in enumerate(blocks):
        score = _score_block(block, keywords)
        if index == 0:
            score += 3
        score += _score_block(block, shared)
        scored.append((score, index, block))

    chosen: list[str] = []
    used_chars = 0
    for score, _, block in sorted(scored, key=lambda item: (-item[0], item[1])):
        if score <= 0:
            continue
        if used_chars + len(block) > max_chars and chosen:
            continue
        chosen.append(block)
        used_chars += len(block)
        if used_chars >= max_chars:
            break

    if not chosen:
        for block in blocks:
            if used_chars + len(block) > max_chars and chosen:
                break
            chosen.append(block)
            used_chars += len(block)
    return chosen


def _default_focus(department_id: str, metadata: dict) -> str:
    spec = DEPARTMENTS[department_id]
    return (
        f"Aportar a la propuesta lo que corresponde a {spec['label']}: "
        f"{spec['requires']}."
    )


def _clean_keywords(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ][:12]


def build_plan(metadata: dict, markdown: str, llm: JsonLlm) -> list[dict]:
    """Devuelve los workstreams activos. Lista vacía = RFP fuera de alcance."""

    active = departments_for_services(metadata.get("services_requested", []))
    if not active:
        return []

    allowed = ", ".join(active)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Departamentos permitidos: [{allowed}]\n\n"
                f"Metadatos de la RFP:\n{json.dumps(metadata, ensure_ascii=False)}\n\n"
                f"--- RFP (extracto) ---\n{markdown[:MAX_PLAN_INPUT_CHARS]}\n--- FIN ---"
            ),
        },
    ]

    llm_workstreams: dict[str, dict] = {}
    try:
        payload = llm(messages, max_tokens=900, temperature=0.0)
        workstreams = payload.get("workstreams")
        if isinstance(workstreams, list):
            for item in workstreams:
                if not isinstance(item, dict):
                    continue
                department_id = item.get("department_id")
                if department_id in active:
                    llm_workstreams[department_id] = item
    except LlmError as exc:
        logger.warning(
            "rfp_intake orquestador sin LLM; se usa plan determinista: %s", exc
        )

    plan: list[dict] = []
    for department_id in active:
        spec = DEPARTMENTS[department_id]
        proposal = llm_workstreams.get(department_id, {})
        focus = proposal.get("focus")
        if not isinstance(focus, str) or not focus.strip():
            focus = _default_focus(department_id, metadata)
        keywords = list(DEPARTMENT_KEYWORDS[department_id])
        for keyword in _clean_keywords(proposal.get("excerpt_keywords")):
            if keyword not in keywords:
                keywords.append(keyword)
        plan.append(
            {
                "department_id": department_id,
                "responsible": spec["responsible"],
                "focus": focus.strip()[:600],
                "excerpt_keywords": keywords,
                "excerpts": select_excerpts(markdown, keywords),
            }
        )

    logger.info(
        "rfp_intake orchestrator departments=%s excluded=%s",
        active,
        [
            department
            for department in DEPARTMENT_ORDER
            if department not in active
        ],
    )
    return plan
