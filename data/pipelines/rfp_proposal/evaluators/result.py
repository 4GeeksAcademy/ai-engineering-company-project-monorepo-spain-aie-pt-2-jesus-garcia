"""Forma estructurada del resultado de evaluación de una sección."""

from __future__ import annotations

from . import readability as readability_evaluator
from . import relevance as relevance_evaluator
from . import compliance as compliance_evaluator


def _readability_feedback(block: dict) -> list[str]:
    details = block.get("details") or {}
    reasons = details.get("failures") or []
    lines = [
        "Legibilidad insuficiente: "
        + ", ".join(reasons)
        + f" (score {block.get('score')})."
    ]
    for sentence in (details.get("longest_sentences") or [])[:3]:
        lines.append(f'  · Acorta o divide: "{sentence}"')
    return lines


def _relevance_feedback(block: dict) -> list[str]:
    details = block.get("details") or {}
    lines: list[str] = []
    missing = block.get("missing_aspects") or []
    if missing:
        lines.append(
            "Aspectos de la RFP sin responder: " + "; ".join(missing) + "."
        )
    missing_questions = details.get("missing_questions") or []
    if missing_questions:
        lines.append(
            "Preguntas abiertas del handoff que no se han conservado: "
            + "; ".join(missing_questions)
            + "."
        )
    if details.get("llm_notes"):
        lines.append(f"Nota del evaluador: {details['llm_notes']}")
    return lines


def _compliance_feedback(block: dict) -> list[str]:
    lines: list[str] = []
    for violation in block.get("violations") or []:
        line = f"[{violation.get('rule_id')}] {violation.get('message')}"
        if violation.get("excerpt"):
            line += f' Cita: "{violation["excerpt"]}"'
        if violation.get("required_change"):
            line += f" Cambio requerido: {violation['required_change']}"
        lines.append(line)
    return lines


def feedback_for_generator(
    readability: dict,
    relevance: dict,
    compliance: dict,
) -> str:
    """Feedback concreto y accionable: regla, cita y cambio exigido."""

    lines: list[str] = []
    if not readability.get("pass"):
        lines.extend(_readability_feedback(readability))
    if not relevance.get("pass"):
        lines.extend(_relevance_feedback(relevance))
    if not compliance.get("pass"):
        lines.extend(_compliance_feedback(compliance))
    if not lines:
        return ""
    return "\n".join(f"{index}. {line}" for index, line in enumerate(lines, 1))[:4_000]


def aggregate_evaluation(
    *,
    section_id: str,
    department_id: str,
    iteration: int,
    readability: dict,
    relevance: dict,
    compliance: dict,
) -> dict:
    overall_pass = bool(
        readability.get("pass")
        and relevance.get("pass")
        and compliance.get("pass")
    )
    result = {
        "section_id": section_id,
        "department_id": department_id,
        "iteration": iteration,
        "readability": readability,
        "relevance": relevance,
        "compliance": compliance,
        "overall_pass": overall_pass,
        "feedback_for_generator": (
            ""
            if overall_pass
            else feedback_for_generator(readability, relevance, compliance)
        ),
    }
    return result


def evaluate_section(
    *,
    brief: dict,
    draft: dict,
    iteration: int,
    llm=None,
) -> dict:
    """Ejecuta los tres evaluadores. El grafo los corre en paralelo; este
    helper secuencial existe para tests y scripts."""

    readability = readability_evaluator.evaluate_readability(draft)
    relevance = relevance_evaluator.evaluate_relevance(brief, draft, llm=llm)
    compliance = compliance_evaluator.evaluate_compliance(brief, draft)
    return aggregate_evaluation(
        section_id=f"{brief['ticket_id']}:{brief['department_id']}",
        department_id=brief["department_id"],
        iteration=iteration,
        readability=readability,
        relevance=relevance,
        compliance=compliance,
    )


__all__ = [
    "aggregate_evaluation",
    "evaluate_section",
    "feedback_for_generator",
]
