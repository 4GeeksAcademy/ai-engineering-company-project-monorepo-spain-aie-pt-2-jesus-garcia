"""Subgrafo generador-evaluador para una sección de departamento.

    generate ──Send──> evaluate_readability ┐
                     > evaluate_relevance    ├─> collect ──> decide
                     > evaluate_compliance  ┘     ▲            │
                                                  └── generate ┘ (con feedback)
                                                               └─ exhausted → needs_human_review

El ciclo está acotado por ``max_iterations``. Los tres evaluadores escriben
solo su propia clave del estado y el nodo ``collect`` es el único que agrega
y persiste, así que no hay escrituras en conflicto.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .evaluators import (
    aggregate_evaluation,
    evaluate_compliance,
    evaluate_readability,
    evaluate_relevance,
)
from .generators import DepartmentGenerator
from .handoff import (
    SECTION_EVALUATING,
    SECTION_GENERATING,
    SECTION_NEEDS_REVIEW,
    SECTION_PASSED,
    TICKET_EVALUATING,
)
from .state import SectionState

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 2


def _event(stage: str, **extra) -> dict:
    return {"stage": stage, **extra}


def build_section_graph(
    *,
    repo,
    llm,
    generator: DepartmentGenerator,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
):
    department_id = generator.department_id

    def generate(state: SectionState) -> dict:
        ticket_id = state["ticket_id"]
        brief = state["brief"]
        iteration = int(state.get("iteration") or 0) + 1
        previous = state.get("draft")
        previous_result = state.get("result") or {}
        feedback = previous_result.get("feedback_for_generator") if previous else None

        repo.save_section_status(
            ticket_id,
            department_id=department_id,
            status=SECTION_GENERATING,
        )
        draft = generator.generate(
            brief,
            llm,
            previous_draft=previous,
            feedback=feedback,
            iteration=iteration,
        )
        repo.save_draft(
            ticket_id,
            department_id=department_id,
            draft=draft,
            iteration=iteration,
        )
        return {
            "draft": draft,
            "iteration": iteration,
            "events": [
                _event(
                    "generate",
                    department_id=department_id,
                    iteration=iteration,
                    with_feedback=bool(feedback),
                    warning=draft.get("generation_warning"),
                )
            ],
        }

    def evaluate_readability_node(state: SectionState) -> dict:
        return {"evaluations": {"readability": evaluate_readability(state["draft"])}}

    def evaluate_relevance_node(state: SectionState) -> dict:
        return {
            "evaluations": {
                "relevance": evaluate_relevance(
                    state["brief"], state["draft"], llm=llm
                )
            }
        }

    def evaluate_compliance_node(state: SectionState) -> dict:
        return {
            "evaluations": {
                "compliance": evaluate_compliance(state["brief"], state["draft"])
            }
        }

    def collect(state: SectionState) -> dict:
        ticket_id = state["ticket_id"]
        brief = state["brief"]
        draft = state["draft"]
        iteration = int(state.get("iteration") or 1)
        evaluations = state.get("evaluations") or {}
        result = aggregate_evaluation(
            section_id=f"{ticket_id}:{department_id}",
            department_id=department_id,
            iteration=iteration,
            readability=evaluations["readability"],
            relevance=evaluations["relevance"],
            compliance=evaluations["compliance"],
        )
        repo.save_evaluation(
            ticket_id,
            department_id=department_id,
            evaluation=result,
        )
        repo.set_ticket_status(ticket_id, TICKET_EVALUATING)
        repo.save_section_status(
            ticket_id,
            department_id=department_id,
            status=SECTION_PASSED if result["overall_pass"] else SECTION_EVALUATING,
        )
        return {
            "result": result,
            "events": [
                _event(
                    "collect",
                    department_id=department_id,
                    iteration=iteration,
                    overall_pass=result["overall_pass"],
                    readability_pass=result["readability"]["pass"],
                    relevance_pass=result["relevance"]["pass"],
                    compliance_pass=result["compliance"]["pass"],
                )
            ],
        }

    def exhausted(state: SectionState) -> dict:
        ticket_id = state["ticket_id"]
        result = state.get("result") or {}
        draft = state.get("draft") or {}
        reason = result.get("feedback_for_generator") or (
            "Se agotó el límite de iteraciones sin superar la evaluación."
        )
        warning = draft.get("generation_warning")
        if warning:
            reason = f"{reason}\nGeneración degradada: {warning}"
        repo.save_section_status(
            ticket_id,
            department_id=department_id,
            status=SECTION_NEEDS_REVIEW,
            review_reason=reason,
        )
        logger.warning(
            "rfp_proposal sección %s del ticket %s agotó iteraciones",
            department_id,
            ticket_id,
        )
        return {
            "status": SECTION_NEEDS_REVIEW,
            "events": [
                _event(
                    "exhausted",
                    department_id=department_id,
                    iterations=state.get("iteration"),
                )
            ],
        }

    def fan_out_evaluators(state: SectionState):
        return [
            Send(
                "evaluate_readability",
                {
                    "ticket_id": state["ticket_id"],
                    "brief": state["brief"],
                    "draft": state["draft"],
                    "iteration": state["iteration"],
                },
            ),
            Send(
                "evaluate_relevance",
                {
                    "ticket_id": state["ticket_id"],
                    "brief": state["brief"],
                    "draft": state["draft"],
                    "iteration": state["iteration"],
                },
            ),
            Send(
                "evaluate_compliance",
                {
                    "ticket_id": state["ticket_id"],
                    "brief": state["brief"],
                    "draft": state["draft"],
                    "iteration": state["iteration"],
                },
            ),
        ]

    def decide(state: SectionState) -> str:
        result = state.get("result") or {}
        if result.get("overall_pass"):
            return END
        limit = int(state.get("max_iterations") or max_iterations)
        if int(state.get("iteration") or 0) >= limit:
            return "exhausted"
        return "generate"

    builder = StateGraph(SectionState)
    builder.add_node("generate", generate)
    builder.add_node("evaluate_readability", evaluate_readability_node)
    builder.add_node("evaluate_relevance", evaluate_relevance_node)
    builder.add_node("evaluate_compliance", evaluate_compliance_node)
    builder.add_node("collect", collect)
    builder.add_node("exhausted", exhausted)

    builder.add_edge(START, "generate")
    builder.add_conditional_edges(
        "generate",
        fan_out_evaluators,
        ["evaluate_readability", "evaluate_relevance", "evaluate_compliance"],
    )
    builder.add_edge("evaluate_readability", "collect")
    builder.add_edge("evaluate_relevance", "collect")
    builder.add_edge("evaluate_compliance", "collect")
    builder.add_conditional_edges(
        "collect",
        decide,
        {"generate": "generate", "exhausted": "exhausted", END: END},
    )
    builder.add_edge("exhausted", END)

    return builder.compile()
