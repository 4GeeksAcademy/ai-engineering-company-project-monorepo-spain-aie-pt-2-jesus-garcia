"""Integración del grafo de propuesta con LLM y repositorio falsos."""

from __future__ import annotations

from rfp_proposal_support import (
    ScriptedProposalLlm,
    InMemoryProposalRepo,
    luna_handoff,
    modaviva_handoff,
    prose,
    run_proposal,
)


def _generators(handoff: dict) -> dict[str, dict]:
    return {
        department["department_id"]: prose(
            aspects=[aspect["aspect"] for aspect in department["key_aspects"]]
        )
        for department in handoff["departments"]
    }


def test_modaviva_end_to_end_only_active_departments():
    handoff = modaviva_handoff()
    llm = ScriptedProposalLlm(generators=_generators(handoff))
    repo = InMemoryProposalRepo(handoff)

    repo, result = run_proposal(handoff, llm=llm, repo=repo, max_iterations=2)

    assert result["status"] == "esperando_aprobación"
    assert repo.ticket["status"] == "esperando_aprobación"
    assert set(repo.sections) == {"warehouse", "reverse"}

    proposal = repo.proposal_handoff
    assert proposal["contract_version"] == "rfp-proposal-v1"
    assert [section["department_id"] for section in proposal["sections"]] == [
        "warehouse",
        "reverse",
    ]
    assert proposal["currency"] == "EUR"
    assert proposal["needs_human_review_sections"] == []
    for section in proposal["sections"]:
        assert section["draft_content"]
        assert section["evaluation_results"]["overall_pass"] is True
        assert section["evaluation_results"]["readability"]["pass"] is True
        assert section["evaluation_results"]["compliance"]["pass"] is True
        assert section["provisional"] is False


def test_luna_quotes_in_usd_with_american_carriers():
    handoff = luna_handoff()
    llm = ScriptedProposalLlm(generators=_generators(handoff))
    repo = InMemoryProposalRepo(handoff)

    repo, result = run_proposal(handoff, llm=llm, repo=repo, max_iterations=2)

    assert result["status"] == "esperando_aprobación"
    sections = {
        section["department_id"]: section
        for section in repo.proposal_handoff["sections"]
    }
    assert set(sections) == {"warehouse", "lastmile"}
    assert repo.proposal_handoff["currency"] == "USD"

    warehouse_storage = next(
        row
        for row in sections["warehouse"]["draft_payload"]["pricing"]
        if row["concept"] == "Almacenamiento"
    )
    assert warehouse_storage["currency"] == "USD"
    assert warehouse_storage["amount"] == 18

    carriers = sections["lastmile"]["draft_payload"]["carriers"]
    assert {carrier["carrier"] for carrier in carriers} >= {"UPS", "FedEx", "DHL"}
    assert sections["lastmile"]["evaluation_results"]["compliance"]["pass"] is True


def test_handoff_metrics_and_status_are_recorded():
    handoff = modaviva_handoff()
    llm = ScriptedProposalLlm(generators=_generators(handoff))
    repo = InMemoryProposalRepo(handoff)

    run_proposal(handoff, llm=llm, repo=repo, max_iterations=2)

    metrics = repo.proposal_handoff["metrics"]
    assert metrics["sections"] == 2
    assert metrics["average_iterations"] == 1.0
    assert repo.proposal_handoff["source_handoff"]["contract_version"] == (
        "rfp-intake-v1"
    )
    assert "generando_borrador" in repo.status_history
    assert "en_evaluación" in repo.status_history
