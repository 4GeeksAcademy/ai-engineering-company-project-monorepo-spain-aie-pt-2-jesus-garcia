"""Ciclo generador-evaluador: reintentos, límite y handoff a revisión."""

from __future__ import annotations

from rfp_proposal_support import (
    InMemoryProposalRepo,
    ScriptedProposalLlm,
    modaviva_handoff,
    prose,
    run_proposal,
    warehouse_only_handoff,
)


def _aspects(handoff: dict, department_id: str) -> list[str]:
    department = next(
        item
        for item in handoff["departments"]
        if item["department_id"] == department_id
    )
    return [aspect["aspect"] for aspect in department["key_aspects"]]


def test_failed_section_retries_with_feedback_then_passes():
    handoff = warehouse_only_handoff()
    aspects = _aspects(handoff, "warehouse")
    llm = ScriptedProposalLlm(
        generators={
            "warehouse": [
                prose(aspects=[]),
                prose(aspects=aspects),
            ]
        }
    )

    repo, result = run_proposal(handoff, llm=llm, max_iterations=2)

    assert llm.generator_calls == ["warehouse", "warehouse"]
    assert [iteration for _, iteration, _ in repo.drafts] == [1, 2]
    evaluations = [evaluation for _, evaluation in repo.evaluations]
    assert evaluations[0]["overall_pass"] is False
    assert evaluations[1]["overall_pass"] is True
    assert result["status"] == "esperando_aprobación"
    assert any(
        "Aspectos de la RFP sin responder" in message[-1]["content"]
        for message in llm.messages
    )


def test_exhausted_section_keeps_last_draft_and_evaluation():
    handoff = warehouse_only_handoff()
    llm = ScriptedProposalLlm(generators={"warehouse": prose(aspects=[])})

    repo, result = run_proposal(handoff, llm=llm, max_iterations=2)

    assert result["status"] == "needs_human_review"
    assert repo.ticket["status"] == "needs_human_review"
    assert repo.sections["warehouse"]["status"] == "needs_human_review"
    assert repo.sections["warehouse"]["draft"]["body_markdown"].strip()
    assert repo.sections["warehouse"]["evaluation"]["overall_pass"] is False

    section = repo.proposal_handoff["sections"][0]
    assert section["provisional"] is True
    assert section["approval_status"] == "needs_human_review"
    assert section["draft_content"]
    assert section["evaluation_results"]["relevance"]["missing_aspects"]
    assert repo.proposal_handoff["needs_human_review_sections"] == ["warehouse"]


def test_failing_department_does_not_block_the_other():
    handoff = modaviva_handoff()
    reverse_aspects = _aspects(handoff, "reverse")
    llm = ScriptedProposalLlm(
        generators={
            "warehouse": prose(aspects=[]),
            "reverse": prose(aspects=reverse_aspects),
        }
    )

    repo, result = run_proposal(handoff, llm=llm, max_iterations=2)

    assert result["status"] == "needs_human_review"
    assert repo.sections["warehouse"]["status"] == "needs_human_review"
    assert repo.sections["reverse"]["status"] == "evaluated_pass"

    sections = {
        section["department_id"]: section
        for section in repo.proposal_handoff["sections"]
    }
    assert sections["warehouse"]["provisional"] is True
    assert sections["reverse"]["provisional"] is False
    assert sections["reverse"]["evaluation_results"]["overall_pass"] is True


def test_iteration_limit_is_enforced():
    handoff = warehouse_only_handoff()
    llm = ScriptedProposalLlm(generators={"warehouse": prose(aspects=[])})

    repo, result = run_proposal(handoff, llm=llm, max_iterations=1)

    assert llm.generator_calls == ["warehouse"]
    assert len(repo.evaluations) == 1
    assert result["status"] == "needs_human_review"


def test_ticket_status_reflects_generation_and_evaluation():
    handoff = warehouse_only_handoff()
    aspects = _aspects(handoff, "warehouse")
    llm = ScriptedProposalLlm(generators={"warehouse": prose(aspects=aspects)})
    repo = InMemoryProposalRepo(handoff)

    run_proposal(handoff, llm=llm, repo=repo, max_iterations=2)

    assert repo.status_history[0] == "generando_borrador"
    assert "en_evaluación" in repo.status_history
    assert repo.ticket["status"] == "esperando_aprobación"
