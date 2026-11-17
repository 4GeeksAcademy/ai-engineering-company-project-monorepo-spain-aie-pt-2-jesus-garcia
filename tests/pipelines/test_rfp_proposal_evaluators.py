"""Tests de los evaluadores de legibilidad, pertinencia y cumplimiento."""

from __future__ import annotations

import copy

from data.pipelines.rfp_proposal.contract import (
    briefs_for_handoff,
    parse_intake_handoff,
)
from data.pipelines.rfp_proposal.evaluators import (
    aggregate_evaluation,
    evaluate_compliance,
    evaluate_readability,
    evaluate_relevance,
)
from data.pipelines.rfp_proposal.generators import generator_for
from rfp_proposal_support import (
    ScriptedProposalLlm,
    luna_handoff,
    modaviva_handoff,
    prose,
)


def _brief(department_id: str = "warehouse") -> dict:
    handoff = luna_handoff() if department_id == "lastmile" else modaviva_handoff()
    parsed = parse_intake_handoff(handoff, ticket_id=handoff["ticket_id"])
    return {
        brief["department_id"]: brief for brief in briefs_for_handoff(parsed)
    }[department_id]


def _draft(brief: dict) -> dict:
    aspects = [aspect["aspect"] for aspect in brief["key_aspects"]]
    llm = ScriptedProposalLlm(
        generators={brief["department_id"]: prose(aspects=aspects)}
    )
    return generator_for(brief["department_id"]).generate(brief, llm)


# --- legibilidad -------------------------------------------------------------


def test_readability_passes_a_well_structured_section():
    result = evaluate_readability(_draft(_brief()))

    assert result["pass"] is True
    assert result["score"] >= 50
    assert result["details"]["word_count"] >= 60


def test_readability_fails_a_too_short_section():
    result = evaluate_readability({"body_markdown": "# Sección\n\nMuy corta."})

    assert result["pass"] is False
    assert any("palabras" in failure for failure in result["details"]["failures"])


def test_readability_fails_a_run_on_sentence():
    long_sentence = " ".join(["TrackFlow gestiona la operación"] * 20) + "."
    markdown = " ".join([long_sentence] * 4)

    result = evaluate_readability({"body_markdown": markdown})

    assert result["pass"] is False
    assert any("palabras por frase" in failure for failure in result["details"]["failures"])


# --- pertinencia -------------------------------------------------------------


def test_relevance_fails_when_a_key_aspect_is_missing():
    brief = _brief()
    draft = _draft(brief)
    draft["addresses_aspects"] = []

    result = evaluate_relevance(brief, draft)

    assert result["pass"] is False
    assert result["missing_aspects"] == ["Volumen de SKUs"]


def test_relevance_fails_when_handoff_questions_are_lost():
    brief = _brief()
    draft = _draft(brief)
    draft["open_questions"] = []
    draft["body_markdown"] = draft["body_markdown"].replace(
        brief["open_questions"][0], ""
    )

    result = evaluate_relevance(brief, draft)

    assert result["pass"] is False
    assert result["details"]["missing_questions"]


def test_relevance_passes_and_reports_llm_usage():
    brief = _brief()
    draft = _draft(brief)
    llm = ScriptedProposalLlm(relevance={"missing_aspects": [], "notes": ""})

    result = evaluate_relevance(brief, draft, llm=llm)

    assert result["pass"] is True
    assert result["details"]["llm_used"] is True


# --- cumplimiento ------------------------------------------------------------


def test_compliance_passes_a_section_built_from_policy():
    brief = _brief()

    result = evaluate_compliance(brief, _draft(brief))

    assert result["pass"] is True, result["violations"]
    assert "BRIEFING-5.2-SLA-90" in result["rule_ids"]


def test_compliance_fails_when_returns_are_promised_under_48_hours():
    """Regla anclada al BRIEFING §5: fixture mínimo + aserción de fallo."""

    brief = _brief("reverse")
    draft = _draft(brief)
    draft["body_markdown"] += (
        "\n\nProcesamos las devoluciones en 24 horas para que el stock vuelva "
        "a estar disponible.\n"
    )

    result = evaluate_compliance(brief, draft)

    assert result["pass"] is False


def test_compliance_flags_the_48_hour_rule_with_excerpt_and_change():
    brief = _brief("reverse")
    draft = _draft(brief)
    draft["body_markdown"] += "\n\nProcesamos las devoluciones en 24 horas.\n"

    result = evaluate_compliance(brief, draft)

    violation = next(
        item
        for item in result["violations"]
        if item["rule_id"] == "BRIEFING-5.3-RETURNS-48H"
    )
    assert "24 horas" in violation["excerpt"]
    assert "48" in violation["required_change"]


def test_compliance_fails_on_currency_mismatch():
    brief = _brief()
    draft = copy.deepcopy(_draft(brief))
    draft["pricing"][0]["currency"] = "USD"

    result = evaluate_compliance(brief, draft)

    assert result["pass"] is False
    assert any(
        violation["rule_id"] == "BRIEFING-5.1-CURRENCY"
        for violation in result["violations"]
    )


def test_compliance_fails_when_carrier_rates_leak():
    brief = _brief("lastmile")
    draft = _draft(brief)
    draft["body_markdown"] += "\n| UPS | 4,20 USD por paquete |\n"

    result = evaluate_compliance(brief, draft)

    assert any(
        violation["rule_id"] == "BRIEFING-5.5-CARRIER-RATES-CONFIDENTIAL"
        for violation in result["violations"]
    )


def test_compliance_fails_without_volume_discount_table():
    brief = _brief()
    draft = copy.deepcopy(_draft(brief))
    draft["discount_tiers"] = []

    result = evaluate_compliance(brief, draft)

    assert any(
        violation["rule_id"] == "BRIEFING-5.4-VOLUME-DISCOUNTS"
        for violation in result["violations"]
    )


def test_compliance_fails_with_a_different_sla():
    brief = _brief()
    draft = copy.deepcopy(_draft(brief))
    draft["sla"]["on_time_pct"] = 85

    result = evaluate_compliance(brief, draft)

    assert any(
        violation["rule_id"] == "BRIEFING-5.2-SLA-90"
        for violation in result["violations"]
    )


def test_feedback_for_generator_names_rule_and_excerpt():
    brief = _brief("reverse")
    draft = _draft(brief)
    draft["body_markdown"] += "\n\nProcesamos las devoluciones en 12 horas.\n"

    evaluation = aggregate_evaluation(
        section_id="ticket-1:reverse",
        department_id="reverse",
        iteration=1,
        readability=evaluate_readability(draft),
        relevance=evaluate_relevance(brief, draft),
        compliance=evaluate_compliance(brief, draft),
    )

    assert evaluation["overall_pass"] is False
    assert "BRIEFING-5.3-RETURNS-48H" in evaluation["feedback_for_generator"]
    assert "12 horas" in evaluation["feedback_for_generator"]
