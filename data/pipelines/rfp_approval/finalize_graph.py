"""Grafo de cierre: gate de cumplimiento y documento final consolidado."""

from __future__ import annotations

import logging
import time

from langgraph.graph import END, START, StateGraph

from .contracts import (
    APPROVAL_APPROVED,
    TICKET_FINISHED,
    TICKET_NEEDS_REVIEW,
    briefs_from_intake,
    expected_currency,
    normalize_intake,
    normalize_proposal,
)
from .final_document import build_final_document, final_gate
from .state import ApprovalState
from .trace import trace_event

logger = logging.getLogger(__name__)


def build_finalize_graph(*, repo):
    def load_approvals(state: ApprovalState) -> dict:
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
        sections = repo.get_sections(ticket_id)
        return {
            "ticket_id": ticket_id,
            "proposal": proposal,
            "intake": intake,
            "briefs": briefs_from_intake(intake),
            "sections": sections,
            "currency": expected_currency(intake, proposal),
            "events": [
                trace_event(
                    part=3,
                    node="load_approvals",
                    agent="document_synthesizer",
                    input={"ticket_id": ticket_id},
                    output={
                        "departments": sorted(sections),
                        "approved": [
                            department
                            for department, section in sections.items()
                            if section.get("approval_status") == APPROVAL_APPROVED
                        ],
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def gate(state: ApprovalState) -> dict:
        started = time.perf_counter()
        result = final_gate(
            state["sections"],
            briefs=state.get("briefs") or {},
            proposal=state["proposal"],
            intake=state.get("intake") or {},
            currency=state.get("currency"),
        )
        return {
            "gate": result,
            "events": [
                trace_event(
                    part=3,
                    node="final_gate",
                    agent="compliance_gate",
                    input={
                        "departments": sorted(state["sections"]),
                        "currency": state.get("currency"),
                    },
                    output={
                        "ok": result["ok"],
                        "violations": [
                            violation.get("rule_id")
                            for violation in result["violations"]
                        ],
                        "rejected_sections": result.get("rejected_sections"),
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def generate_document(state: ApprovalState) -> dict:
        started = time.perf_counter()
        document = build_final_document(
            ticket_id=state["ticket_id"],
            proposal=state["proposal"],
            intake=state.get("intake") or {},
            sections=state["sections"],
            currency=state.get("currency"),
        )
        path = repo.save_final_document(
            state["ticket_id"], document=document
        )
        return {
            "final_document": document,
            "events": [
                trace_event(
                    part=3,
                    node="generate_document",
                    agent="document_synthesizer",
                    input={
                        "departments": sorted(state["sections"]),
                        "currency": state.get("currency"),
                    },
                    output={
                        "contract_version": document["contract_version"],
                        "sections": len(document["sections"]),
                        "approved_by": [
                            item.get("approver")
                            for item in document.get("approved_by") or []
                        ],
                        "path": path,
                        "chars": len(document.get("markdown") or ""),
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def complete(state: ApprovalState) -> dict:
        started = time.perf_counter()
        gate_result = state.get("gate") or {}
        generated = bool(state.get("final_document"))
        status = (
            TICKET_FINISHED
            if gate_result.get("ok") and generated
            else TICKET_NEEDS_REVIEW
        )
        repo.set_approval_ticket_status(
            state["ticket_id"],
            status,
            approval_status="completed" if status == TICKET_FINISHED else "rejected",
            stage=status,
            completed=status == TICKET_FINISHED,
        )
        return {
            "status": status,
            "events": [
                trace_event(
                    part=3,
                    node="complete",
                    agent="document_synthesizer",
                    input={
                        "gate_ok": bool(gate_result.get("ok")),
                        "document_ready": generated,
                    },
                    output={
                        "ticket_status": status,
                        "document_contract": (
                            (state.get("final_document") or {}).get(
                                "contract_version"
                            )
                        ),
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            ],
        }

    def route_after_gate(state: ApprovalState) -> str:
        return (
            "generate_document"
            if (state.get("gate") or {}).get("ok")
            else "complete"
        )

    builder = StateGraph(ApprovalState)
    builder.add_node("load_approvals", load_approvals)
    builder.add_node("final_gate", gate)
    builder.add_node("generate_document", generate_document)
    builder.add_node("complete", complete)

    builder.add_edge(START, "load_approvals")
    builder.add_edge("load_approvals", "final_gate")
    builder.add_conditional_edges(
        "final_gate",
        route_after_gate,
        ["generate_document", "complete"],
    )
    builder.add_edge("generate_document", "complete")
    builder.add_edge("complete", END)
    return builder.compile()


__all__ = ["build_finalize_graph"]
