"""Grafo exterior de la Parte 2: del handoff a las secciones evaluadas.

    load_handoff → plan → Send(department) × N (paralelo) → finalize_proposal

Cada departamento ejecuta su propio subgrafo generador-evaluador. Los
departamentos no se bloquean entre sí: uno puede agotar iteraciones y quedar
``needs_human_review`` mientras otro termina aprobado.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .contract import (
    HandoffContractError,
    briefs_for_handoff,
    parse_intake_handoff,
)
from .generators import GENERATORS, generator_for
from .handoff import (
    PROPOSAL_NEEDS_REVIEW,
    PROPOSAL_READY,
    SECTION_NEEDS_REVIEW,
    SECTION_PASSED,
    TICKET_DRAFTING,
    build_proposal_handoff,
)
from .section_graph import DEFAULT_MAX_ITERATIONS, build_section_graph
from .state import ProposalState

logger = logging.getLogger(__name__)

REQUIRED_TICKET_STATUSES = frozenset(
    {"analisis_completo", "needs_human_review", "esperando_aprobación"}
)
REQUIRED_HANDOFF_STATUS = "ready"


def _event(stage: str, **extra) -> dict:
    from datetime import datetime, timezone

    agent = extra.pop("agent", None)
    if agent is None:
        if stage == "department":
            agent = f"generator:{extra.get('department_id') or 'departamento'}"
        elif stage in {"generate", "collect", "exhausted"}:
            agent = (
                f"generator:{extra.get('department_id') or 'departamento'}"
                if stage == "generate"
                else f"evaluator:{extra.get('department_id') or 'departamento'}"
            )
        elif stage == "load_handoff":
            agent = "proposal_orchestrator"
        elif stage == "finalize_proposal":
            agent = "proposal_orchestrator"
        else:
            agent = "proposal_orchestrator"
    return {
        "stage": stage,
        "agent": agent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def build_proposal_graph(
    *,
    repo,
    llm,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
):
    section_graphs = {
        department_id: build_section_graph(
            repo=repo,
            llm=llm,
            generator=generator_for(department_id),
            max_iterations=max_iterations,
        )
        for department_id in GENERATORS
    }

    def load_handoff(state: ProposalState) -> dict:
        ticket_id = state["ticket_id"]
        ticket = repo.get_ticket(ticket_id)
        if ticket.get("status") not in REQUIRED_TICKET_STATUSES:
            raise HandoffContractError(
                "La Parte 2 solo consume tickets listos de la Parte 1 "
                f"(ticket en {ticket.get('status')!r})."
            )
        if ticket.get("handoff_status") != REQUIRED_HANDOFF_STATUS:
            raise HandoffContractError(
                "El ticket no tiene el handoff de la Parte 1 marcado como listo."
            )
        handoff = parse_intake_handoff(
            ticket.get("handoff_payload"),
            ticket_id=ticket_id,
            fallback_facts=repo.get_rfp_facts(ticket_id),
        )
        repo.set_ticket_status(
            ticket_id,
            TICKET_DRAFTING,
            stage=TICKET_DRAFTING,
            force=True,
        )
        briefs = briefs_for_handoff(handoff)
        return {
            "handoff": handoff,
            "briefs": briefs,
            "max_iterations": max_iterations,
            "status": TICKET_DRAFTING,
            "events": [
                _event(
                    "load_handoff",
                    departments=[brief["department_id"] for brief in briefs],
                    contract_version=handoff["contract_version"],
                )
            ],
        }

    def dispatch_departments(state: ProposalState):
        return [
            Send(
                "department",
                {
                    "ticket_id": state["ticket_id"],
                    "brief": brief,
                    "max_iterations": state.get("max_iterations", max_iterations),
                },
            )
            for brief in state.get("briefs", [])
        ]

    def department(state: ProposalState) -> dict:
        ticket_id = state["ticket_id"]
        brief = state["brief"]
        department_id = brief["department_id"]
        graph = section_graphs[department_id]
        section_state = graph.invoke(
            {
                "ticket_id": ticket_id,
                "brief": brief,
                "max_iterations": state.get("max_iterations", max_iterations),
                "evaluations": {},
                "events": [],
            },
            config={"recursion_limit": 60},
        )
        draft = section_state.get("draft") or {}
        evaluation = section_state.get("result") or {}
        status = section_state.get("status") or (
            SECTION_PASSED
            if evaluation.get("overall_pass")
            else SECTION_NEEDS_REVIEW
        )
        section = {
            **draft,
            "evaluation_results": evaluation,
            "status": status,
            "iteration_count": section_state.get("iteration") or 0,
        }
        if status == SECTION_NEEDS_REVIEW:
            section["review_reason"] = evaluation.get("feedback_for_generator")
        section_events = list(section_state.get("events") or [])
        return {
            "sections": {department_id: section},
            "events": [
                *section_events,
                _event(
                    "department",
                    department_id=department_id,
                    status=status,
                    iterations=section.get("iteration_count"),
                    overall_pass=evaluation.get("overall_pass"),
                ),
            ],
        }

    def finalize_proposal(state: ProposalState) -> dict:
        ticket_id = state["ticket_id"]
        handoff = state["handoff"]
        sections = state.get("sections", {})
        proposal_handoff = build_proposal_handoff(
            ticket_id=ticket_id,
            rfp_id=handoff.get("rfp_id"),
            intake=handoff,
            sections=sections,
        )
        needs_review = proposal_handoff["status"] == PROPOSAL_NEEDS_REVIEW
        status = PROPOSAL_NEEDS_REVIEW if needs_review else PROPOSAL_READY
        repo.complete_proposal(ticket_id, handoff=proposal_handoff, status=status)
        logger.info(
            "rfp_proposal ticket=%s status=%s sections=%s review=%s",
            ticket_id,
            status,
            len(proposal_handoff["sections"]),
            proposal_handoff["needs_human_review_sections"],
        )
        return {
            "proposal_handoff": proposal_handoff,
            "status": status,
            "events": [
                _event(
                    "finalize_proposal",
                    status=status,
                    review_sections=proposal_handoff["needs_human_review_sections"],
                    average_iterations=proposal_handoff["metrics"][
                        "average_iterations"
                    ],
                )
            ],
        }

    builder = StateGraph(ProposalState)
    builder.add_node("load_handoff", load_handoff)
    builder.add_node("department", department)
    builder.add_node("finalize_proposal", finalize_proposal)

    builder.add_edge(START, "load_handoff")
    builder.add_conditional_edges(
        "load_handoff",
        dispatch_departments,
        ["department"],
    )
    builder.add_edge("department", "finalize_proposal")
    builder.add_edge("finalize_proposal", END)

    return builder.compile()
