"""Grafo de arbitraje: detecta conflictos y aplica el árbitro fijo."""

from __future__ import annotations

import logging
import time
from typing import Callable

from langgraph.graph import END, START, StateGraph

from .conflicts import (
    ARBITRATOR_MIGUEL,
    TRIGGER_CURRENCY,
    TRIGGER_RETURNS_SLA,
    TRIGGER_VOLUME_CAPACITY,
    cap_section_volume,
    capacity_signal,
    detect_conflicts,
    regeneration_feedback,
    rewrite_section_currency,
)
from .contracts import (
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    TICKET_NEEDS_REVIEW,
    briefs_from_intake,
    expected_currency,
    normalize_intake,
    normalize_proposal,
    proposal_sections,
)
from .state import ApprovalState
from .trace import trace_event, utc_now

logger = logging.getLogger(__name__)

RegenerateFn = Callable[[str, str, dict, str, int], dict]


def _default_max_rounds() -> int:
    import os

    try:
        return max(1, int(os.getenv("RFP_APPROVAL_MAX_ROUNDS", "2")))
    except ValueError:
        return 2


def build_arbitration_graph(
    *,
    repo,
    regenerate: RegenerateFn,
    max_rounds: int | None = None,
):
    limit = max_rounds or _default_max_rounds()

    def load_proposal(state: ApprovalState) -> dict:
        started = time.perf_counter()
        ticket_id = state["ticket_id"]
        ticket = repo.get_ticket(ticket_id)
        proposal = normalize_proposal(
            repo.get_proposal(ticket_id) or ticket.get("proposal_payload"),
            ticket_id=ticket_id,
        )
        intake = normalize_intake(
            repo.get_intake_handoff(ticket_id), ticket_id=ticket_id
        )
        sections = repo.get_sections(ticket_id) or proposal_sections(proposal)
        if not sections:
            raise ValueError("La propuesta no tiene secciones que arbitrar.")
        briefs = briefs_from_intake(intake)
        currency = expected_currency(intake, proposal)
        return {
            "ticket_id": ticket_id,
            "rfp_id": proposal.get("rfp_id"),
            "proposal": proposal,
            "intake": intake,
            "briefs": briefs,
            "sections": sections,
            "currency": currency,
            "conflicts": [],
            "arbitration_round": 0,
            "max_rounds": limit,
            "status": None,
            "events": [
                trace_event(
                    part=3,
                    node="load_proposal",
                    agent="approval_orchestrator",
                    input={"ticket_id": ticket_id},
                    output={
                        "departments": sorted(sections),
                        "currency": currency,
                        "sections": len(sections),
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def detect(state: ApprovalState) -> dict:
        started = time.perf_counter()
        conflicts = detect_conflicts(
            state["sections"],
            briefs=state.get("briefs") or {},
            proposal=state["proposal"],
            intake=state.get("intake") or {},
            currency=state.get("currency"),
        )
        return {
            "conflicts": conflicts,
            "events": [
                trace_event(
                    part=3,
                    node="detect_conflicts",
                    agent="conflict_detector",
                    input={
                        "departments": sorted(state["sections"]),
                        "round": state.get("arbitration_round", 0),
                    },
                    output={
                        "conflicts": [conflict["trigger_id"] for conflict in conflicts],
                        "count": len(conflicts),
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def _resolve(
        conflict: dict,
        sections: dict[str, dict],
        *,
        round_no: int,
    ) -> tuple[dict[str, dict], dict]:
        trigger = conflict["trigger_id"]
        affected = list(conflict.get("affected_sections") or [])
        regenerations: list[dict] = []
        action = "none"

        if trigger == TRIGGER_CURRENCY:
            expected = (conflict.get("evidence") or {}).get("expected_currency")
            for department_id in affected:
                sections[department_id] = rewrite_section_currency(
                    sections[department_id], expected
                )
            action = "rewrite_currency"

        elif trigger == TRIGGER_VOLUME_CAPACITY:
            capacity = capacity_signal(sections.get("warehouse") or {})
            if capacity is not None:
                for department_id in affected:
                    sections[department_id] = cap_section_volume(
                        sections[department_id], capacity
                    )
                action = "cap_volume"
            else:
                action = "request_changes"

        elif trigger == TRIGGER_RETURNS_SLA:
            action = "request_changes"

        if action == "request_changes":
            for department_id in affected:
                regenerations.append(
                    {
                        "department_id": department_id,
                        "feedback": regeneration_feedback(conflict, department_id),
                    }
                )

        resolution = {
            "trigger_id": trigger,
            "arbitrator": conflict.get("arbitrator"),
            "rule": conflict.get("rule"),
            "action": action,
            "affected_sections": affected,
            "requires_regeneration": [
                item["department_id"] for item in regenerations
            ],
            "round": round_no,
            "resolved": action != "request_changes",
            "details": conflict.get("evidence") or {},
            "resolved_at": utc_now(),
        }
        return sections, {
            "resolution": resolution,
            "regenerations": regenerations,
        }

    def arbitrate(state: ApprovalState) -> dict:
        started = time.perf_counter()
        ticket_id = state["ticket_id"]
        round_no = int(state.get("arbitration_round") or 0) + 1
        sections = dict(state["sections"])
        results: list[dict] = []

        for conflict in state.get("conflicts") or []:
            sections, payload = _resolve(conflict, sections, round_no=round_no)
            resolution = payload["resolution"]
            if resolution["action"] in {"rewrite_currency", "cap_volume"}:
                for department_id in resolution["affected_sections"]:
                    repo.save_section_snapshot(
                        ticket_id, section=sections[department_id]
                    )
            for item in payload["regenerations"]:
                department_id = item["department_id"]
                updated = regenerate(
                    ticket_id,
                    department_id,
                    sections[department_id],
                    item["feedback"],
                    round_no,
                )
                updated = {
                    **updated,
                    "department_id": department_id,
                    "approval_status": APPROVAL_PENDING,
                    "approval_round": max(
                        int(updated.get("approval_round") or 0), round_no
                    ),
                    "provisional": bool(updated.get("needs_human_review")),
                }
                sections[department_id] = updated
                repo.save_section_snapshot(ticket_id, section=updated)
            repo.record_arbitration(
                ticket_id,
                round=round_no,
                conflict=conflict,
                resolution=resolution,
            )
            results.append(resolution)

        return {
            "sections": sections,
            "arbitration_round": round_no,
            "arbitration_results": results,
            "events": [
                trace_event(
                    part=3,
                    node="arbitrate",
                    agent=(
                        results[0]["arbitrator"]
                        if results
                        else ARBITRATOR_MIGUEL
                    ),
                    input={
                        "round": round_no,
                        "conflicts": [
                            conflict["trigger_id"]
                            for conflict in state.get("conflicts") or []
                        ],
                    },
                    output={
                        "resolutions": [
                            {
                                "trigger_id": item["trigger_id"],
                                "action": item["action"],
                                "resolved": item["resolved"],
                            }
                            for item in results
                        ]
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def reject_unresolved(state: ApprovalState) -> dict:
        started = time.perf_counter()
        ticket_id = state["ticket_id"]
        round_no = int(state.get("arbitration_round") or 0)
        sections = dict(state["sections"])
        decided_at = utc_now()
        affected: list[str] = []
        for conflict in state.get("conflicts") or []:
            for department_id in conflict.get("affected_sections") or []:
                if department_id not in sections:
                    continue
                affected.append(department_id)
                section = {
                    **sections[department_id],
                    "approval_status": APPROVAL_REJECTED,
                    "approver": conflict.get("arbitrator"),
                    "approved_at": None,
                    "approval_comment": (
                        f"{conflict.get('rule')} "
                        f"(trigger: {conflict.get('trigger_id')})."
                    ),
                    "approval_round": round_no,
                    "review_reason": conflict.get("rule"),
                }
                sections[department_id] = section
                repo.save_approval_decision(
                    ticket_id,
                    department_id=department_id,
                    status=APPROVAL_REJECTED,
                    approver=conflict.get("arbitrator"),
                    comment=section["approval_comment"],
                    decided_at=decided_at,
                    approval_round=round_no,
                )
                repo.save_section_snapshot(ticket_id, section=section)
        return {
            "sections": sections,
            "status": TICKET_NEEDS_REVIEW,
            "events": [
                trace_event(
                    part=3,
                    node="reject_unresolved",
                    agent="arbitration_gate",
                    input={
                        "round": round_no,
                        "conflicts": [
                            conflict["trigger_id"]
                            for conflict in state.get("conflicts") or []
                        ],
                    },
                    output={
                        "rejected_sections": sorted(set(affected)),
                        "reason": "max_rounds_reached",
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def route_after_detect(state: ApprovalState) -> str:
        if not state.get("conflicts"):
            return END
        if int(state.get("arbitration_round") or 0) >= int(
            state.get("max_rounds") or limit
        ):
            return "reject_unresolved"
        return "arbitrate"

    builder = StateGraph(ApprovalState)
    builder.add_node("load_proposal", load_proposal)
    builder.add_node("detect_conflicts", detect)
    builder.add_node("arbitrate", arbitrate)
    builder.add_node("reject_unresolved", reject_unresolved)

    builder.add_edge(START, "load_proposal")
    builder.add_edge("load_proposal", "detect_conflicts")
    builder.add_conditional_edges(
        "detect_conflicts",
        route_after_detect,
        ["arbitrate", "reject_unresolved", END],
    )
    builder.add_edge("arbitrate", "detect_conflicts")
    builder.add_edge("reject_unresolved", END)
    return builder.compile()


__all__ = ["RegenerateFn", "build_arbitration_graph"]
