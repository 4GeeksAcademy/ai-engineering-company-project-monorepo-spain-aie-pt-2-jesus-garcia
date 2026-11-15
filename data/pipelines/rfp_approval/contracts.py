"""Contratos de entrada/salida y validación de la Parte 3.

La Parte 3 consume el payload ``rfp-proposal-v1`` de la Parte 2 y el handoff
``rfp-intake-v1`` de la Parte 1. La validación de la decisión humana ocurre
**antes** de tocar el checkpointer y se repite dentro del nodo de aprobación
(defensa en profundidad).
"""

from __future__ import annotations

import logging
from typing import Final

from data.pipelines.rfp_intake.catalog import DEPARTMENTS, DEPARTMENT_ORDER

logger = logging.getLogger(__name__)

PROPOSAL_CONTRACT: Final[str] = "rfp-proposal-v1"
FINAL_CONTRACT: Final[str] = "rfp-final-v1"

TICKET_AWAITING: Final[str] = "esperando_aprobación"
TICKET_FINISHED: Final[str] = "terminado"
TICKET_NEEDS_REVIEW: Final[str] = "needs_human_review"
TICKET_EVALUATING: Final[str] = "en_evaluación"

APPROVAL_PENDING: Final[str] = "pending_approval"
APPROVAL_APPROVED: Final[str] = "approved"
APPROVAL_REJECTED: Final[str] = "rejected"
APPROVAL_CHANGES: Final[str] = "changes_requested"

APPROVAL_ACTIONS: Final[tuple[str, ...]] = (
    "approve",
    "reject",
    "request_changes",
)

DEFAULT_MAX_ROUNDS: Final[int] = 2


class ApprovalError(ValueError):
    """Error controlado del flujo de aprobación."""


class ApprovalDecisionError(ApprovalError):
    """La decisión humana no cumple el contrato."""


class ApprovalStateError(ApprovalError):
    """El ticket o la sección no están en el estado esperado."""


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _list(value: object) -> list:
    return list(value) if isinstance(value, list) else []


def _dict(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def normalize_proposal(payload: dict | None, *, ticket_id: str) -> dict:
    """Valida la forma mínima del handoff de la Parte 2."""

    if not isinstance(payload, dict) or not payload:
        raise ApprovalStateError(
            "El ticket no tiene propuesta de la Parte 2 (proposal_payload vacío)."
        )
    if payload.get("contract_version") != PROPOSAL_CONTRACT:
        raise ApprovalStateError(
            "Contrato de propuesta no soportado: "
            f"{payload.get('contract_version')!r}. Se esperaba {PROPOSAL_CONTRACT}."
        )
    proposal_ticket = payload.get("ticket_id")
    if proposal_ticket and proposal_ticket != ticket_id:
        raise ApprovalStateError(
            f"La propuesta pertenece a otro ticket: {proposal_ticket} != {ticket_id}."
        )
    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ApprovalStateError(
            "La propuesta no incluye secciones activas que aprobar."
        )

    sections: dict[str, dict] = {}
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        department_id = item.get("department_id")
        if department_id not in DEPARTMENTS:
            raise ApprovalStateError(
                f"Departamento fuera del catálogo cerrado: {department_id!r}."
            )
        if department_id in sections:
            raise ApprovalStateError(
                f"Departamento duplicado en la propuesta: {department_id}."
            )
        spec = DEPARTMENTS[department_id]
        sections[department_id] = {
            **item,
            "department_id": department_id,
            "department_label": item.get("department_label") or spec["label"],
            "responsible": item.get("responsible") or spec["responsible"],
            "draft_content": item.get("draft_content") or "",
            "draft_payload": _dict(item.get("draft_payload")),
            "evaluation_results": _dict(item.get("evaluation_results")),
            "approval_status": item.get("approval_status") or APPROVAL_PENDING,
            "approver": item.get("approver"),
            "approved_at": item.get("approved_at"),
            "approval_comment": item.get("approval_comment"),
            "approval_round": int(item.get("approval_round") or 0),
            "iteration_count": int(item.get("iteration_count") or 0),
            "provisional": bool(
                item.get("provisional")
                or item.get("approval_status") == "needs_human_review"
            ),
            "review_reason": item.get("review_reason"),
        }

    if not sections:
        raise ApprovalStateError("La propuesta no incluye ningún departamento válido.")

    ordered = {
        department: sections[department]
        for department in DEPARTMENT_ORDER
        if department in sections
    }
    return {
        "contract_version": PROPOSAL_CONTRACT,
        "ticket_id": payload.get("ticket_id") or ticket_id,
        "rfp_id": payload.get("rfp_id"),
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "client": _dict(payload.get("client")),
        "client_country": payload.get("client_country"),
        "currency": payload.get("currency"),
        "services_requested": _list(payload.get("services_requested")),
        "sections": ordered,
        "needs_human_review_sections": _list(
            payload.get("needs_human_review_sections")
        ),
        "metrics": _dict(payload.get("metrics")),
        "facts": _dict(payload.get("facts")),
    }


def proposal_sections(payload: dict) -> dict[str, dict]:
    return _dict(payload.get("sections"))


def expected_currency(intake: dict, proposal: dict) -> str | None:
    return (
        intake.get("currency")
        or proposal.get("currency")
        or (intake.get("client") or {}).get("currency")
    )


def normalize_intake(intake: dict | None, *, ticket_id: str) -> dict:
    """Normaliza el handoff de la Parte 1 para leer `facts` y `departments`."""

    if not isinstance(intake, dict) or not intake:
        return {}
    from data.pipelines.rfp_proposal.contract import (
        HandoffContractError,
        parse_intake_handoff,
    )

    try:
        return parse_intake_handoff(intake, ticket_id=ticket_id)
    except (HandoffContractError, KeyError, TypeError, ValueError):
        logger.warning(
            "Handoff de la Parte 1 no normalizable; se usa el payload crudo."
        )
        if "facts" not in intake:
            return {**intake, "facts": intake.get("rfp_facts") or {}}
        return intake


def briefs_from_intake(intake: dict | None) -> dict[str, dict]:
    """Briefs por departamento para regenerar una sección con la Parte 2."""

    if not isinstance(intake, dict) or not intake:
        return {}
    from data.pipelines.rfp_proposal.contract import (
        HandoffContractError,
        briefs_for_handoff,
    )

    try:
        already_normalized = (
            isinstance(intake, dict)
            and "facts" in intake
            and "departments" in intake
            and "status" not in intake
        )
        normalized = (
            intake
            if already_normalized
            else normalize_intake(
                intake, ticket_id=intake.get("ticket_id") or ""
            )
        )
        briefs = briefs_for_handoff(normalized)
    except (HandoffContractError, KeyError, TypeError, ValueError):
        logger.warning("Handoff de la Parte 1 no reutilizable para regenerar.")
        return {}
    return {brief["department_id"]: brief for brief in briefs}


def fallback_brief(section: dict, *, proposal: dict, intake: dict | None) -> dict:
    """Brief mínimo si no hay handoff de la Parte 1 (tickets antiguos)."""

    payload = _dict(section.get("draft_payload"))
    addresses = _list(payload.get("addresses_aspects"))
    facts = _dict((intake or {}).get("facts"))
    return {
        "ticket_id": proposal.get("ticket_id"),
        "rfp_id": proposal.get("rfp_id"),
        "client": _dict(proposal.get("client")),
        "client_country": proposal.get("client_country"),
        "currency": proposal.get("currency"),
        "services_requested": _list(proposal.get("services_requested")),
        "facts": facts,
        "department_id": section.get("department_id"),
        "department_label": section.get("department_label"),
        "responsible": section.get("responsible"),
        "focus": "",
        "key_aspects": [
            {
                "aspect": str(aspect),
                "detail": "",
                "evidence": "",
                "confidence": "medium",
            }
            for aspect in addresses
        ],
        "open_questions": _list(payload.get("open_questions")),
        "questions_to_ask": [],
        "conflicts": [],
    }


def build_approval_packet(
    section: dict,
    *,
    proposal: dict,
    intake: dict | None,
    conflicts: list[dict],
    max_rounds: int,
) -> dict:
    """Información mínima para que un humano decida sin releer el documento."""

    payload = _dict(section.get("draft_payload"))
    approval_round = int(section.get("approval_round") or 0)
    packet = {
        "ticket_id": proposal.get("ticket_id"),
        "rfp_id": proposal.get("rfp_id"),
        "department_id": section.get("department_id"),
        "department_label": section.get("department_label"),
        "responsible": section.get("responsible"),
        "client": _dict(proposal.get("client")),
        "client_country": proposal.get("client_country"),
        "currency": proposal.get("currency"),
        "services_requested": _list(proposal.get("services_requested")),
        "deadline": _dict((intake or {}).get("facts")).get("deadline"),
        "section_markdown": section.get("draft_content") or "",
        "title": payload.get("title"),
        "executive_summary": payload.get("executive_summary"),
        "pricing": _list(payload.get("pricing")),
        "sla": _dict(payload.get("sla")),
        "discount_tiers": _list(payload.get("discount_tiers")),
        "turnaround": _dict(payload.get("turnaround")),
        "capacity": _dict(payload.get("capacity")),
        "carriers": _list(payload.get("carriers")),
        "assumptions": _list(payload.get("assumptions")),
        "open_questions": _list(payload.get("open_questions")),
        "addresses_aspects": _list(payload.get("addresses_aspects")),
        "evaluation": _dict(section.get("evaluation_results")),
        "provisional": bool(section.get("provisional")),
        "review_reason": section.get("review_reason"),
        "iteration_count": int(section.get("iteration_count") or 0),
        "approval_round": approval_round,
        "max_rounds": max_rounds,
        "conflicts": [
            conflict
            for conflict in conflicts
            if section.get("department_id") in (conflict.get("affected_sections") or [])
        ],
        "allowed_actions": (
            ["approve", "reject"]
            if approval_round >= max_rounds
            else list(APPROVAL_ACTIONS)
        ),
        "decision_requirements": {
            "approver_must_be": section.get("responsible"),
            "comment_required_for": ["reject", "request_changes"],
            "provisional_requires_comment": bool(section.get("provisional")),
        },
    }
    return packet


def normalize_decision(decision: dict | None) -> dict:
    if not isinstance(decision, dict):
        raise ApprovalDecisionError("La decisión humana debe ser un objeto.")
    action = _text(decision.get("action"))
    if action not in APPROVAL_ACTIONS:
        raise ApprovalDecisionError(
            f"Acción no válida: {action!r}. Usa {', '.join(APPROVAL_ACTIONS)}."
        )
    return {
        "action": action,
        "approver": _text(decision.get("approver")),
        "comment": _text(decision.get("comment")),
        "interrupt_id": _text(decision.get("interrupt_id")),
        "acknowledge_provisional": bool(decision.get("acknowledge_provisional")),
    }


def validate_decision(
    decision: dict | None,
    *,
    section: dict,
    max_rounds: int,
) -> dict:
    """Valida la respuesta humana antes de reanudar el grafo."""

    normalized = normalize_decision(decision)
    responsible = _text(section.get("responsible"))
    if not normalized["approver"]:
        raise ApprovalDecisionError("Falta el nombre del aprobador.")
    if responsible and normalized["approver"].casefold() != responsible.casefold():
        raise ApprovalDecisionError(
            "El aprobador debe ser el responsable del departamento: "
            f"{responsible}."
        )
    if not normalized["interrupt_id"]:
        raise ApprovalDecisionError("Falta el interrupt_id de la aprobación pendiente.")

    action = normalized["action"]
    if action in {"reject", "request_changes"} and not normalized["comment"]:
        raise ApprovalDecisionError(
            f"La acción {action} requiere un comentario explicativo."
        )
    if action == "approve" and section.get("provisional"):
        if not normalized["acknowledge_provisional"]:
            raise ApprovalDecisionError(
                "La sección es provisional: confirma explícitamente la "
                "aceptación (acknowledge_provisional)."
            )
        if not normalized["comment"]:
            raise ApprovalDecisionError(
                "Aprobar una sección provisional requiere un comentario."
            )
    if action == "request_changes":
        approval_round = int(section.get("approval_round") or 0)
        if approval_round >= max_rounds:
            raise ApprovalDecisionError(
                "Se alcanzó el límite de rondas de revisión: solo se puede "
                "aprobar o rechazar la sección."
            )
    return normalized


def is_approved(section: dict) -> bool:
    return section.get("approval_status") == APPROVAL_APPROVED


def is_rejected(section: dict) -> bool:
    return section.get("approval_status") == APPROVAL_REJECTED


__all__ = [
    "APPROVAL_ACTIONS",
    "APPROVAL_APPROVED",
    "APPROVAL_CHANGES",
    "APPROVAL_PENDING",
    "APPROVAL_REJECTED",
    "DEFAULT_MAX_ROUNDS",
    "FINAL_CONTRACT",
    "PROPOSAL_CONTRACT",
    "TICKET_AWAITING",
    "TICKET_EVALUATING",
    "TICKET_FINISHED",
    "TICKET_NEEDS_REVIEW",
    "ApprovalDecisionError",
    "ApprovalError",
    "ApprovalStateError",
    "briefs_from_intake",
    "build_approval_packet",
    "expected_currency",
    "fallback_brief",
    "is_approved",
    "is_rejected",
    "normalize_decision",
    "normalize_intake",
    "normalize_proposal",
    "proposal_sections",
    "validate_decision",
]
