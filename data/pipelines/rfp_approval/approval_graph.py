"""Grafo de aprobación de una rama de departamento.

Cada departamento tiene su propio hilo y su propio checkpoint
(``rfp-{ticket}:run-{n}:{department}``). La pausa de una rama no toca a las
demás. ``request_changes`` regenera solo esa sección reutilizando la Parte 2.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .contracts import (
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    TICKET_AWAITING,
    build_approval_packet,
    validate_decision,
)
from ..rfp_intake.sanitize import sanitize_document_text
from .state import BranchState
from .trace import trace_event, utc_now

logger = logging.getLogger(__name__)

RegenerateFn = Callable[[str, str, dict, str, int], dict]


def build_approval_branch_graph(
    *,
    repo,
    regenerate: RegenerateFn,
    checkpointer,
    max_rounds: int = 2,
):
    def prepare_approval(state: BranchState) -> dict:
        started = time.perf_counter()
        ticket_id = state["ticket_id"]
        department_id = state["department_id"]
        section = state["section"]
        context = state.get("context") or {}
        approval_round = int(
            state.get("approval_round") or section.get("approval_round") or 0
        )
        packet = build_approval_packet(
            {**section, "approval_round": approval_round},
            proposal=context["proposal"],
            intake=context.get("intake") or {},
            conflicts=context.get("conflicts") or [],
            max_rounds=max_rounds,
        )
        section = {
            **section,
            "approval_status": APPROVAL_PENDING,
            "approval_round": approval_round,
        }
        repo.save_approval_packet(
            ticket_id,
            department_id=department_id,
            packet=packet,
            approval_round=approval_round,
        )
        return {
            "packet": packet,
            "section": section,
            "approval_round": approval_round,
            "status": TICKET_AWAITING,
            "events": [
                trace_event(
                    part=3,
                    node="prepare_approval",
                    agent="approval_coordinator",
                    department_id=department_id,
                    input={
                        "ticket_id": ticket_id,
                        "department_id": department_id,
                        "round": approval_round,
                    },
                    output={
                        "approver": section.get("responsible"),
                        "allowed_actions": packet.get("allowed_actions"),
                        "provisional": packet.get("provisional"),
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def await_approval(state: BranchState) -> dict:
        started = time.perf_counter()
        department_id = state["department_id"]
        packet = state["packet"]
        decision = interrupt(packet)
        validated = validate_decision(
            decision,
            section=state["section"],
            max_rounds=max_rounds,
        )
        return {
            "decision": validated,
            "events": [
                trace_event(
                    part=3,
                    node="await_approval",
                    agent=f"human:{validated['approver']}",
                    department_id=department_id,
                    input={
                        "department_id": department_id,
                        "round": state.get("approval_round"),
                        "pending_actions": packet.get("allowed_actions"),
                    },
                    output={
                        "action": validated["action"],
                        "comment": validated.get("comment") or "",
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def record_approval(state: BranchState) -> dict:
        started = time.perf_counter()
        ticket_id = state["ticket_id"]
        department_id = state["department_id"]
        decision = state["decision"]
        decided_at = utc_now()
        section = {
            **state["section"],
            "approval_status": APPROVAL_APPROVED,
            "approver": decision["approver"],
            "approved_at": decided_at,
            "approval_comment": decision.get("comment") or None,
            "approval_round": int(state.get("approval_round") or 0),
            "provisional": bool(state["section"].get("provisional")),
            "review_reason": state["section"].get("review_reason"),
        }
        repo.save_approval_decision(
            ticket_id,
            department_id=department_id,
            status=APPROVAL_APPROVED,
            approver=decision["approver"],
            comment=decision.get("comment"),
            decided_at=decided_at,
            approval_round=section["approval_round"],
        )
        repo.save_section_snapshot(ticket_id, section=section)
        return {
            "section": section,
            "status": APPROVAL_APPROVED,
            "events": [
                trace_event(
                    part=3,
                    node="record_approval",
                    agent=f"human:{decision['approver']}",
                    department_id=department_id,
                    input={
                        "department_id": department_id,
                        "action": "approve",
                        "round": section["approval_round"],
                    },
                    output={
                        "approval_status": APPROVAL_APPROVED,
                        "approver": decision["approver"],
                        "approved_at": decided_at,
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def record_rejection(state: BranchState) -> dict:
        started = time.perf_counter()
        ticket_id = state["ticket_id"]
        department_id = state["department_id"]
        decision = state.get("decision") or {}
        comment = decision.get("comment") or (
            "Se alcanzó el límite de rondas de revisión."
        )
        decided_at = utc_now()
        section = {
            **state["section"],
            "approval_status": APPROVAL_REJECTED,
            "approver": decision.get("approver") or state["section"].get("responsible"),
            "approved_at": None,
            "approval_comment": comment,
            "approval_round": int(state.get("approval_round") or 0),
            "review_reason": comment,
        }
        repo.save_approval_decision(
            ticket_id,
            department_id=department_id,
            status=APPROVAL_REJECTED,
            approver=section["approver"],
            comment=comment,
            decided_at=decided_at,
            approval_round=section["approval_round"],
        )
        repo.save_section_snapshot(ticket_id, section=section)
        return {
            "section": section,
            "status": APPROVAL_REJECTED,
            "events": [
                trace_event(
                    part=3,
                    node="record_rejection",
                    agent=f"human:{section['approver']}",
                    department_id=department_id,
                    input={
                        "department_id": department_id,
                        "action": "reject",
                        "round": section["approval_round"],
                    },
                    output={
                        "approval_status": APPROVAL_REJECTED,
                        "comment": comment,
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def regenerate_section(state: BranchState) -> dict:
        started = time.perf_counter()
        ticket_id = state["ticket_id"]
        department_id = state["department_id"]
        decision = state.get("decision") or {}
        next_round = int(state.get("approval_round") or 0) + 1
        if next_round > max_rounds:
            return {
                "decision": {
                    **decision,
                    "action": "reject",
                    "comment": (
                        "Se alcanzó el límite de rondas de revisión "
                        f"({max_rounds})."
                    ),
                },
                "status": APPROVAL_REJECTED,
                "events": [
                    trace_event(
                        part=3,
                        node="regenerate_section",
                        agent="approval_coordinator",
                        department_id=department_id,
                        input={"round": state.get("approval_round")},
                        output={
                            "skipped": True,
                            "reason": "max_rounds_reached",
                        },
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                ],
            }
        feedback = sanitize_document_text(
            str(decision.get("comment") or "")
        )
        updated = regenerate(
            ticket_id,
            department_id,
            state["section"],
            feedback.text,
            next_round,
        )
        updated = {
            **updated,
            "department_id": department_id,
            "approval_status": APPROVAL_PENDING,
            "approval_round": next_round,
            "provisional": bool(updated.get("needs_human_review")),
        }
        repo.save_section_snapshot(ticket_id, section=updated)
        return {
            "section": updated,
            "packet": {},
            "approval_round": next_round,
            "status": APPROVAL_PENDING,
            "events": [
                trace_event(
                    part=3,
                    node="regenerate_section",
                    agent=f"generator:{department_id}",
                    department_id=department_id,
                    input={
                        "department_id": department_id,
                        "feedback": feedback.text,
                        "round": next_round,
                    },
                    output={
                        "iteration_count": updated.get("iteration_count"),
                        "overall_pass": (
                            updated.get("evaluation_results") or {}
                        ).get("overall_pass"),
                        "review_reason": updated.get("review_reason"),
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def route_decision(state: BranchState) -> str:
        action = (state.get("decision") or {}).get("action")
        if action == "approve":
            return "record_approval"
        if action == "reject":
            return "record_rejection"
        if action == "request_changes":
            return "regenerate_section"
        return "record_rejection"

    def route_after_regenerate(state: BranchState) -> str:
        if state.get("status") == APPROVAL_REJECTED:
            return "record_rejection"
        return "prepare_approval"

    builder = StateGraph(BranchState)
    builder.add_node("prepare_approval", prepare_approval)
    builder.add_node("await_approval", await_approval)
    builder.add_node("record_approval", record_approval)
    builder.add_node("record_rejection", record_rejection)
    builder.add_node("regenerate_section", regenerate_section)

    builder.add_edge(START, "prepare_approval")
    builder.add_edge("prepare_approval", "await_approval")
    builder.add_conditional_edges(
        "await_approval",
        route_decision,
        ["record_approval", "record_rejection", "regenerate_section"],
    )
    builder.add_conditional_edges(
        "regenerate_section",
        route_after_regenerate,
        ["prepare_approval", "record_rejection"],
    )
    builder.add_edge("record_approval", END)
    builder.add_edge("record_rejection", END)
    return builder.compile(checkpointer=checkpointer)


__all__ = ["RegenerateFn", "build_approval_branch_graph"]
