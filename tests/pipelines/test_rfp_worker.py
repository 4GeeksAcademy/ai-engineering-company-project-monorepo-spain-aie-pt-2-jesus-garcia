"""Tests del agente worker por departamento."""

from __future__ import annotations

from data.pipelines.rfp_intake.worker import build_section, numeric_tokens
from rfp_support import (
    MODAVIVA,
    ScriptedLlm,
    modaviva_metadata,
    worker_response,
)


def _workstream(department_id: str = "warehouse") -> dict:
    return {
        "department_id": department_id,
        "responsible": "Ana Whitfield",
        "focus": "Capacidad de almacenamiento",
        "excerpts": [MODAVIVA],
    }


def test_worker_returns_key_aspects_with_evidence_from_source():
    llm = ScriptedLlm(workers={"Warehouse Operations": worker_response()})
    section = build_section(_workstream(), modaviva_metadata(), llm)

    assert section["department_id"] == "warehouse"
    assert section["responsible"] == "Ana Whitfield"
    assert section["key_aspects"][0]["aspect"] == "Almacenamiento"
    assert section["key_aspects"][0]["evidence"] == "15.000 SKUs"
    assert section["assumed_facts"]["currency"] == "EUR"
    assert section["unsupported_claims"] == []


def test_worker_records_missing_monthly_volume_as_open_question():
    llm = ScriptedLlm(workers={"Warehouse Operations": worker_response()})
    section = build_section(_workstream(), modaviva_metadata(), llm)

    assert any(
        "volumen mensual" in question for question in section["open_questions"]
    )


def test_worker_drops_invented_numbers_and_asks_to_confirm_them():
    llm = ScriptedLlm(
        workers={
            "Warehouse Operations": {
                "key_aspects": [
                    {
                        "aspect": "Capacidad inventada",
                        "detail": "Necesita 99.999 pallets al mes.",
                        "evidence": "99.999 pallets",
                        "confidence": "high",
                    }
                ],
                "open_questions": [],
                "assumed_facts": {},
            }
        }
    )
    section = build_section(_workstream(), modaviva_metadata(), llm)

    assert section["key_aspects"] == []
    assert section["unsupported_claims"][0]["numbers"] == ["99999"]
    assert any(
        "99999" in question for question in section["open_questions"]
    )


def test_worker_keeps_canonical_facts_when_llm_contradicts_them():
    llm = ScriptedLlm(
        workers={
            "Warehouse Operations": {
                "key_aspects": [
                    {
                        "aspect": "Almacenamiento",
                        "detail": "15.000 SKUs.",
                        "evidence": "15.000 SKUs",
                        "confidence": "high",
                    }
                ],
                "open_questions": [],
                "assumed_facts": {
                    "monthly_volume": 99999,
                    "currency": "USD",
                    "client_country": "US",
                },
            }
        }
    )
    section = build_section(_workstream(), modaviva_metadata(), llm)

    assert section["assumed_facts"]["monthly_volume"] is None
    assert section["assumed_facts"]["currency"] == "EUR"
    assert section["assumed_facts"]["client_country"] == "Spain"
    assert len(section["conflicts"]) == 3
    assert any("canónico" in question for question in section["open_questions"])


def test_numeric_tokens_normalizes_thousands_separators():
    assert numeric_tokens("15.000 SKUs y 5,000 pedidos") == {"15000", "5000"}
    assert numeric_tokens("3PL y 48 h") == {"48"}
