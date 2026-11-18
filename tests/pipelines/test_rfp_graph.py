"""Tests de integración del grafo rfp_intake con LLM y repo falsos."""

from __future__ import annotations

import pytest

from data.pipelines.rfp_intake.runner import RfpPipelineError
from rfp_support import (
    LUNA,
    MODAVIVA,
    RAPIDSHIP,
    ScriptedLlm,
    luna_classification,
    luna_metadata,
    modaviva_classification,
    modaviva_metadata,
    run_pipeline,
    worker_response,
)


def _orchestrator(*departments: str) -> dict:
    labels = {
        "warehouse": "Capacidad de almacenamiento",
        "lastmile": "Envíos y transportistas",
        "reverse": "Devoluciones",
    }
    return {
        "workstreams": [
            {
                "department_id": department,
                "focus": labels[department],
                "excerpt_keywords": [department],
            }
            for department in departments
        ]
    }


def test_modaviva_end_to_end_produces_handoff_for_part_two():
    repo, state, _ = run_pipeline(
        MODAVIVA,
        classifier=modaviva_classification(),
        metadata=modaviva_metadata(),
        orchestrator=_orchestrator("warehouse", "reverse"),
        workers={
            "Warehouse Operations": worker_response("Almacenamiento"),
            "Reverse Logistics": worker_response("Devoluciones"),
        },
        synthesizer={"sales_summary": "- ModaViva (España, EUR) pide almacenamiento y devoluciones."},
    )

    assert state["status"] == "completed"
    assert repo.ticket["status"] == "analisis_completo"
    assert repo.plan == ["warehouse", "reverse"]
    assert set(repo.sections) == {"warehouse", "reverse"}
    assert "lastmile" not in repo.sections

    handoff = repo.handoff
    assert handoff["contract_version"] == "rfp-intake-v1"
    assert handoff["ticket_id"] == "ticket-1"
    assert handoff["currency"] == "EUR"
    assert [item["department_id"] for item in handoff["departments"]] == [
        "warehouse",
        "reverse",
    ]
    assert any(
        "volumen mensual" in item["question"]
        for item in handoff["questions_to_ask"]
    )
    assert repo.readability["estimated_llm_tokens"] > 0
    assert repo.document_metadata["converter"] == "test"


def test_luna_activates_warehouse_and_lastmile_with_usd():
    repo, state, _ = run_pipeline(
        LUNA,
        classifier=luna_classification(),
        metadata=luna_metadata(),
        orchestrator=_orchestrator("warehouse", "lastmile"),
        workers={
            "Warehouse Operations": {
                "key_aspects": [
                    {
                        "aspect": "Volumen",
                        "detail": "La RFP declara 5.000 pedidos al mes.",
                        "evidence": "5,000 orders a month",
                        "confidence": "high",
                    }
                ],
                "open_questions": [],
                "assumed_facts": {
                    "monthly_volume": 5000,
                    "currency": "USD",
                    "client_country": "US",
                },
            },
            "Last Mile and Carrier Management": {
                "key_aspects": [
                    {
                        "aspect": "Carrier selection",
                        "detail": "El cliente no tiene transportistas.",
                        "evidence": "we don't have relationships with any carriers yet",
                        "confidence": "high",
                    }
                ],
                "open_questions": [],
                "assumed_facts": {
                    "monthly_volume": 5000,
                    "currency": "USD",
                    "client_country": "US",
                },
            },
        },
        synthesizer={"sales_summary": "- Luna Cosmetics (US, USD) pide warehousing y última milla."},
    )

    assert state["status"] == "completed"
    assert repo.handoff["currency"] == "USD"
    assert [item["department_id"] for item in repo.handoff["departments"]] == [
        "warehouse",
        "lastmile",
    ]
    assert "reverse" not in repo.sections


def test_carrier_pitch_is_discarded_without_running_workers():
    repo, state, llm = run_pipeline(RAPIDSHIP)

    assert state["status"] == "discarded"
    assert repo.ticket["status"] == "descartado"
    assert repo.sections == {}
    assert "transportista" in repo.discard_kwargs["reason"].lower()
    assert llm.calls == []


def test_rfp_with_only_unknown_services_is_discarded_out_of_scope():
    repo, state, _ = run_pipeline(
        MODAVIVA,
        classifier={
            "is_rfp": True,
            "confidence": 0.8,
            "document_type": "formal_rfp",
            "reason": "Pide un servicio que TrackFlow no ofrece.",
            "services_requested": ["customs_brokerage"],
            "unknown_services": ["customs_brokerage"],
            "client_country": "Spain",
        },
        metadata={
            "client_name": "ModaViva, S.L.",
            "client_country": "Spain",
            "services_requested": ["customs_brokerage"],
            "unknown_services": ["customs_brokerage"],
            "monthly_volume": None,
            "deadline": None,
            "budget_range": None,
        },
        orchestrator={"workstreams": []},
    )

    assert state["status"] == "discarded"
    assert repo.ticket["status"] == "descartado"
    assert "catálogo" in repo.discard_kwargs["reason"]
    assert repo.sections == {}


def test_worker_failure_marks_ticket_as_error():
    class BrokenWorkerLlm(ScriptedLlm):
        def __call__(self, messages, *, max_tokens=1_200, temperature=0.0):
            if "responsable de" in messages[0].get("content", ""):
                raise RuntimeError("proveedor caído")
            return super().__call__(
                messages, max_tokens=max_tokens, temperature=temperature
            )

    from rfp_support import InMemoryRepo

    repo = InMemoryRepo()
    llm = BrokenWorkerLlm(
        classifier=modaviva_classification(),
        metadata=modaviva_metadata(),
        orchestrator=_orchestrator("warehouse"),
    )
    with pytest.raises(RfpPipelineError):
        run_pipeline(
            MODAVIVA,
            repo=repo,
            llm=llm,
        )

    assert repo.ticket["status"] == "error"
    assert repo.failure["stage"].startswith("analizando_")
    assert "RuntimeError" in repo.failure["error"]
