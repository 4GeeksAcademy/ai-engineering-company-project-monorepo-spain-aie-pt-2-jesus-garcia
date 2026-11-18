"""Tests del orquestador: descomposición y alcance por departamento."""

from __future__ import annotations

from data.pipelines.rfp_intake.llm import LlmError
from data.pipelines.rfp_intake.orchestrator import build_plan
from rfp_support import MODAVIVA, ScriptedLlm, modaviva_metadata


def test_modaviva_activates_warehouse_and_reverse_but_not_lastmile():
    llm = ScriptedLlm(
        orchestrator={
            "workstreams": [
                {
                    "department_id": "warehouse",
                    "focus": "Capacidad para 15.000 SKUs",
                    "excerpt_keywords": ["almacenamiento", "SKU"],
                },
                {
                    "department_id": "reverse",
                    "focus": "Procesamiento de devoluciones",
                    "excerpt_keywords": ["devoluciones"],
                },
            ]
        }
    )
    plan = build_plan(modaviva_metadata(), MODAVIVA, llm)

    assert [item["department_id"] for item in plan] == ["warehouse", "reverse"]
    assert all(item["excerpts"] for item in plan)
    assert plan[0]["responsible"] == "Ana Whitfield"
    assert plan[1]["responsible"] == "Sofía Ramos"


def test_orchestrator_cannot_add_a_department_outside_the_catalog():
    llm = ScriptedLlm(
        orchestrator={
            "workstreams": [
                {"department_id": "warehouse", "focus": "Capacidad"},
                {"department_id": "lastmile", "focus": "Envíos inventados"},
                {"department_id": "customs", "focus": "Aduanas"},
            ]
        }
    )
    plan = build_plan(modaviva_metadata(), MODAVIVA, llm)
    assert [item["department_id"] for item in plan] == ["warehouse", "reverse"]


def test_orchestrator_falls_back_to_catalog_when_llm_fails():
    class BrokenLlm:
        def __call__(self, messages, **kwargs):
            raise LlmError("sin proveedor")

    plan = build_plan(modaviva_metadata(), MODAVIVA, BrokenLlm())
    assert [item["department_id"] for item in plan] == ["warehouse", "reverse"]
    assert plan[0]["focus"]


def test_no_known_services_means_no_workstreams():
    metadata = modaviva_metadata()
    metadata["services_requested"] = []
    plan = build_plan(metadata, MODAVIVA, ScriptedLlm())
    assert plan == []


def test_excerpt_selection_keeps_relevant_blocks():
    llm = ScriptedLlm(
        orchestrator={
            "workstreams": [
                {
                    "department_id": "warehouse",
                    "focus": "Almacenamiento",
                    "excerpt_keywords": ["15.000 SKUs"],
                }
            ]
        }
    )
    plan = build_plan(modaviva_metadata(), MODAVIVA, llm)
    joined = " ".join(plan[0]["excerpts"])
    assert "15.000 SKUs" in joined
