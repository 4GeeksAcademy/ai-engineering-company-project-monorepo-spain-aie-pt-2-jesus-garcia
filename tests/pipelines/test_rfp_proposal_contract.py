"""Contrato de entrada de la Parte 2: handoff de la Parte 1."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_proposal.contract import (
    HandoffContractError,
    briefs_for_handoff,
    parse_intake_handoff,
)
from rfp_proposal_support import (
    ScriptedProposalLlm,
    modaviva_handoff,
    prose,
    run_proposal,
)


def test_part_one_handoff_satisfies_part_two_contract():
    handoff = modaviva_handoff()

    parsed = parse_intake_handoff(handoff, ticket_id="ticket-1")

    assert parsed["contract_version"] == "rfp-intake-v1"
    assert [item["department_id"] for item in parsed["departments"]] == [
        "warehouse",
        "reverse",
    ]
    assert parsed["currency"] == "EUR"
    assert parsed["client_country"] == "Spain"
    assert parsed["facts"]["sku_count"] == 15_000
    # Campo aditivo que la Parte 1 añade para cotizar sin reparsear el PDF.
    assert handoff["rfp_facts"]["deadline"] == "2026-08-28"


def test_contract_rejects_unknown_version():
    handoff = modaviva_handoff()
    handoff["contract_version"] = "rfp-intake-v0"

    with pytest.raises(HandoffContractError):
        parse_intake_handoff(handoff, ticket_id="ticket-1")


def test_contract_rejects_ticket_not_marked_ready():
    handoff = modaviva_handoff()
    handoff["status"] = "analizando"

    with pytest.raises(HandoffContractError):
        parse_intake_handoff(handoff, ticket_id="ticket-1")


def test_contract_rejects_department_outside_catalog():
    handoff = modaviva_handoff()
    handoff["departments"][0]["department_id"] = "legal"

    with pytest.raises(HandoffContractError):
        parse_intake_handoff(handoff, ticket_id="ticket-1")


def test_contract_rejects_handoff_from_another_ticket():
    with pytest.raises(HandoffContractError):
        parse_intake_handoff(
            modaviva_handoff(), ticket_id="otro-ticket"
        )


def test_generators_never_touch_the_pdf():
    """El handoff apunta a rutas inexistentes: si se leyera el PDF, fallaría."""

    handoff = modaviva_handoff()
    assert not Path(handoff["source"]["pdf_path"]).exists()
    assert not Path(handoff["source"]["markdown_path"]).exists()

    aspects = {
        item["department_id"]: [a["aspect"] for a in item["key_aspects"]]
        for item in handoff["departments"]
    }
    llm = ScriptedProposalLlm(
        generators={
            department: prose(aspects=values)
            for department, values in aspects.items()
        }
    )

    repo, result = run_proposal(handoff, llm=llm)

    assert result["status"] == "esperando_aprobación"
    assert repo.proposal_handoff["source_handoff"]["handoff_ready"] is True


def test_briefs_are_a_closed_slice_per_department():
    parsed = parse_intake_handoff(modaviva_handoff(), ticket_id="ticket-1")

    briefs = briefs_for_handoff(parsed)

    assert {brief["department_id"] for brief in briefs} == {
        "warehouse",
        "reverse",
    }
    for brief in briefs:
        assert "departments" not in brief
        assert brief["key_aspects"]
