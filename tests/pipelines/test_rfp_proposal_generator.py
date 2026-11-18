"""Tests del agente generador por departamento."""

from __future__ import annotations

from data.pipelines.rfp_proposal.contract import (
    briefs_for_handoff,
    parse_intake_handoff,
)
from data.pipelines.rfp_proposal.generators import generator_for
from rfp_proposal_support import (
    ScriptedProposalLlm,
    luna_handoff,
    modaviva_handoff,
    prose,
)


def _brieves(handoff):
    parsed = parse_intake_handoff(handoff, ticket_id=handoff["ticket_id"])
    return {brief["department_id"]: brief for brief in briefs_for_handoff(parsed)}


def _generate(brief, **prose_kwargs):
    generator = generator_for(brief["department_id"])
    aspects = [aspect["aspect"] for aspect in brief["key_aspects"]]
    llm = ScriptedProposalLlm(
        generators={brief["department_id"]: prose(aspects=aspects, **prose_kwargs)}
    )
    return generator.generate(brief, llm)


def test_warehouse_generator_uses_published_rate_and_currency():
    brief = _brieves(modaviva_handoff())["warehouse"]

    draft = _generate(brief)

    storage = next(
        row for row in draft["pricing"] if row["concept"] == "Almacenamiento"
    )
    assert storage["amount"] == 16
    assert storage["currency"] == "EUR"
    assert draft["currency"] == "EUR"
    assert draft["sla"]["on_time_pct"] == 90
    assert len(draft["discount_tiers"]) >= 2
    assert draft["capacity"]["sku_count"] == 15_000
    assert "Descuentos por volumen" in draft["body_markdown"]
    assert draft["unsupported_claims"] == []


def test_lastmile_generator_uses_us_carriers_and_pending_price():
    brief = _brieves(luna_handoff())["lastmile"]

    draft = _generate(brief)

    carriers = {carrier["carrier"] for carrier in draft["carriers"]}
    assert {"UPS", "FedEx", "DHL"}.issubset(carriers)
    pricing = next(row for row in draft["pricing"] if "envío" in row["concept"])
    assert pricing["currency"] == "USD"
    assert pricing["amount"] is None
    assert pricing["status"] == "pendiente_confirmacion"
    assert draft["sla"]["on_time_pct"] == 90


def test_reverse_generator_never_commits_under_48_hours():
    brief = _brieves(modaviva_handoff())["reverse"]

    draft = _generate(brief)

    assert draft["turnaround"]["minimum_hours"] == 48
    assert draft["turnaround"]["committed_hours"] is None
    assert "48 horas" in draft["body_markdown"]


def test_generator_preserves_handoff_questions_and_missing_volume():
    brief = _brieves(modaviva_handoff())["warehouse"]

    draft = _generate(brief)

    assert any(
        "volumen mensual" in question.lower()
        for question in draft["open_questions"]
    )
    assert "pendiente de confirmación" in draft["body_markdown"].lower()


def test_generator_drops_invented_numbers_and_asks_to_confirm_them():
    brief = _brieves(modaviva_handoff())["warehouse"]
    aspects = [aspect["aspect"] for aspect in brief["key_aspects"]]
    llm = ScriptedProposalLlm(
        generators={
            "warehouse": prose(
                aspects=aspects,
                summary=(
                    "TrackFlow moverá 99.999 pallets al mes y garantiza "
                    "resultados inmediatos."
                ),
            )
        }
    )

    draft = generator_for("warehouse").generate(brief, llm)

    assert draft["unsupported_claims"]
    assert "99999" in draft["unsupported_claims"][0]["numbers"]
    assert "99.999" not in draft["executive_summary"]
    assert any("99999" in question for question in draft["open_questions"])


def test_generator_receives_previous_draft_and_feedback_on_retry():
    brief = _brieves(modaviva_handoff())["warehouse"]
    aspects = [aspect["aspect"] for aspect in brief["key_aspects"]]
    llm = ScriptedProposalLlm(
        generators={"warehouse": prose(aspects=aspects)}
    )
    generator = generator_for("warehouse")
    previous = generator.generate(brief, llm)
    feedback = (
        "[BRIEFING-5.3-RETURNS-48H] La sección promete devoluciones en 24 "
        'horas. Cita: "Procesamos las devoluciones en 24 horas."'
    )

    generator.generate(
        brief,
        llm,
        previous_draft=previous,
        feedback=feedback,
        iteration=2,
    )

    prompt = llm.messages[-1][-1]["content"]
    assert feedback in prompt
    assert "BORRADOR ANTERIOR" in prompt
