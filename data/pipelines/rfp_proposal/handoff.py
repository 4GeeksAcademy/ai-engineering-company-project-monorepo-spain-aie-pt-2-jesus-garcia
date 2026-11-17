"""Handoff de la Parte 2 a la Parte 3 (``rfp-proposal-v1``).

Una sección que agotó iteraciones viaja igualmente al handoff, marcada como
``provisional`` y con su último ``EvaluationResult``. La Parte 3 no puede
tratarla como aprobada.
"""

from __future__ import annotations

from datetime import datetime, timezone

from data.pipelines.rfp_intake.catalog import DEPARTMENT_ORDER

PROPOSAL_READY = "esperando_aprobación"
PROPOSAL_NEEDS_REVIEW = "needs_human_review"
TICKET_DRAFTING = "generando_borrador"
TICKET_EVALUATING = "en_evaluación"

SECTION_PASSED = "evaluated_pass"
SECTION_NEEDS_REVIEW = "needs_human_review"
SECTION_GENERATING = "generando"
SECTION_EVALUATING = "en_evaluación"


def _ordered_sections(sections: dict[str, dict]) -> list[dict]:
    def sort_key(item: tuple[str, dict]) -> int:
        department_id = item[0]
        return (
            DEPARTMENT_ORDER.index(department_id)
            if department_id in DEPARTMENT_ORDER
            else len(DEPARTMENT_ORDER)
        )

    return [
        section
        for _, section in sorted(sections.items(), key=sort_key)
    ]


def build_proposal_handoff(
    *,
    ticket_id: str,
    rfp_id: str | None,
    intake: dict,
    sections: dict[str, dict],
) -> dict:
    ordered = _ordered_sections(sections)
    payload_sections: list[dict] = []
    review_sections: list[str] = []
    iterations: list[int] = []

    for section in ordered:
        department_id = section.get("department_id") or ""
        iteration_count = int(section.get("iteration_count") or 0)
        iterations.append(iteration_count)
        needs_review = section.get("status") == SECTION_NEEDS_REVIEW
        if needs_review:
            review_sections.append(department_id)
        draft_payload = {
            key: value
            for key, value in section.items()
            if key
            not in {
                "body_markdown",
                "evaluation_results",
                "status",
                "review_reason",
                "iteration_count",
            }
        }
        payload_sections.append(
            {
                "section_id": f"{ticket_id}:{department_id}",
                "department_id": department_id,
                "department_label": section.get("department_label"),
                "responsible": section.get("responsible"),
                "status": (
                    SECTION_NEEDS_REVIEW if needs_review else SECTION_PASSED
                ),
                "provisional": needs_review,
                "iteration_count": iteration_count,
                "draft_content": section.get("body_markdown") or "",
                "draft_payload": draft_payload,
                "evaluation_results": section.get("evaluation_results") or {},
                "review_reason": section.get("review_reason"),
                "approval_status": (
                    "needs_human_review" if needs_review else "pending_approval"
                ),
                "approver": None,
                "approved_at": None,
            }
        )

    overall_status = (
        PROPOSAL_NEEDS_REVIEW if review_sections else PROPOSAL_READY
    )
    average_iterations = (
        round(sum(iterations) / len(iterations), 2) if iterations else 0.0
    )
    return {
        "contract_version": "rfp-proposal-v1",
        "ticket_id": ticket_id,
        "rfp_id": rfp_id,
        "status": overall_status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "client": intake.get("client") or {},
        "client_country": intake.get("client_country"),
        "currency": intake.get("currency"),
        "services_requested": intake.get("services_requested") or [],
        "sections": payload_sections,
        "needs_human_review_sections": review_sections,
        "metrics": {
            "sections": len(payload_sections),
            "average_iterations": average_iterations,
            "max_iterations_used": max(iterations) if iterations else 0,
        },
        "source_handoff": {
            "contract_version": intake.get("contract_version"),
            "handoff_ready": True,
        },
    }


__all__ = [
    "PROPOSAL_NEEDS_REVIEW",
    "PROPOSAL_READY",
    "SECTION_NEEDS_REVIEW",
    "SECTION_PASSED",
    "build_proposal_handoff",
]
