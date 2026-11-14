"""Evals del grafo con auto-evaluación de memoria (dobles, sin red ni BD)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.api.app.agent.graph import compile_agent_graph
from services.api.app.agent.memory.generation import generate_with_memory
from services.api.app.agent.memory.scopes import normalize_scope
from services.api.app.agent.memory.schemas import (
    EvaluationOutcome,
    GenerationOutcome,
    MemoryProposalDraft,
)
from services.api.app.agent.runner import run_agent
from services.api.app.agent.tools.contracts import (
    IncidentLookupOutput,
    IncidentRecord,
)
from services.api.app.agent.tracing import AgentTrace

CHUNKS = [
    {
        "company": "trackflow",
        "source_document": "carrier-coverage",
        "section": "Cobertura",
        "chunk_index": 0,
        "text": "SEUR cubre la zona rural de Zaragoza.",
    },
    {
        "company": "trackflow",
        "source_document": "sla-delivery",
        "section": "SLA de Entrega",
        "chunk_index": 0,
        "text": "El envío estándar dentro del mismo país tarda de 3 a 5 días hábiles.",
    },
]

SEUR_MESSAGE = (
    "En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que usar "
    "el carrier local desde el mes pasado."
)
STRIKE_MESSAGE = (
    "Esos retrasos reportados en incidencias de Los Ángeles esta semana son "
    "por la huelga portuaria, no por un problema nuestro — ya van tres "
    "tickets sobre lo mismo."
)


def carrier_proposal() -> MemoryProposalDraft:
    return MemoryProposalDraft(
        memory_type="carrier_rule",
        scope=normalize_scope(
            {"tipo": "carrier", "carrier": "SEUR", "pais": "ES", "zona": "rural"},
            "carrier_rule",
        ),
        fact=(
            "SEUR ya no cubre la zona rural de Zaragoza; usar el carrier "
            "local desde el mes pasado."
        ),
        reason="Corrección de cobertura",
        source_quote="SEUR ya no cubre esa zona rural de Zaragoza",
    )


def ops_proposal() -> MemoryProposalDraft:
    return MemoryProposalDraft(
        memory_type="operational_context",
        scope=normalize_scope(
            {"tipo": "ops", "sitio": "los_angeles", "pais": "US"},
            "operational_context",
        ),
        fact=(
            "Los retrasos en Los Ángeles se deben a una huelga portuaria, "
            "no a un problema de TrackFlow."
        ),
        reason="Patrón recurrente",
        source_quote="son por la huelga portuaria",
    )


def incident_record() -> IncidentRecord:
    return IncidentRecord(
        id="482",
        title="Retraso",
        description="Retraso en la entrega",
        description_excerpt="Retraso en la entrega",
        origin="customer",
        branch="la_warehouse",
        category="carrier_issue",
        status="open",
        created_at="2026-11-01T10:00:00+00:00",
        updated_at="2026-11-01T10:00:00+00:00",
    )


def forbidden(*args, **kwargs):
    pytest.fail("No debía ejecutarse esa fuente para esta pregunta.")


def run_traced(
    tmp_path: Path,
    question: str,
    *,
    retriever,
    memory_generator=None,
    generator=None,
    incident_lookup=None,
    memory_evaluator=None,
    memory_gate=None,
    memory_context=None,
    user=None,
):
    graph = compile_agent_graph(
        retriever=retriever,
        generator=generator,
        memory_generator=memory_generator,
        incident_lookup=incident_lookup,
        memory_evaluator=memory_evaluator,
        memory_gate=memory_gate,
    )
    result = run_agent(
        question,
        graph=graph,
        trace_dir=tmp_path,
        user=user,
        memory_context=memory_context,
    )
    return result, AgentTrace.load(result.trace_path)


def node_event(trace: AgentTrace, node: str):
    for event in trace.events:
        if event.node == node:
            return event
    raise AssertionError(f"El trace no contiene el nodo {node}")


def test_rag_generates_answer_and_proposal_in_a_single_call(tmp_path):
    calls = {"n": 0}

    def memory_generator(question, context, memory_context):
        calls["n"] += 1
        return GenerationOutcome(
            answer=(
                "Según la corrección, SEUR ya no cubre la zona rural de "
                "Zaragoza y hay que usar el carrier local."
            ),
            proposal=carrier_proposal(),
        )

    result, trace = run_traced(
        tmp_path,
        SEUR_MESSAGE,
        retriever=lambda question: CHUNKS,
        memory_generator=memory_generator,
    )

    assert result.status == "ok"
    assert calls["n"] == 1
    assert result.memory_proposal is not None
    assert result.memory_proposal["memory_type"] == "carrier_rule"
    assert trace.node_order == [
        "receive_question",
        "classify",
        "retrieve",
        "generate",
    ]
    assert trace.retrieved_sources[0]["source_document"] == "carrier-coverage"
    assert node_event(trace, "generate").output["memory_proposal"]["fact"].startswith(
        "SEUR ya no cubre"
    )


def test_rag_without_memorable_fact_returns_no_proposal(tmp_path):
    calls = {"n": 0}

    def memory_generator(question, context, memory_context):
        calls["n"] += 1
        return GenerationOutcome(
            answer="El envío estándar tarda de 3 a 5 días hábiles.",
            proposal=None,
        )

    result, trace = run_traced(
        tmp_path,
        "¿Cuál es el SLA de un envío estándar?",
        retriever=lambda question: CHUNKS,
        memory_generator=memory_generator,
    )

    assert result.status == "ok"
    assert result.memory_proposal is None
    assert calls["n"] == 1
    assert node_event(trace, "generate").output["memory_proposal"] is None


def test_tool_lookup_does_not_call_the_memory_evaluator(tmp_path):
    def incident_lookup(payload):
        return IncidentLookupOutput(
            ok=True, found=True, incidents=[incident_record()]
        )

    result, trace = run_traced(
        tmp_path,
        "¿En qué estado está el ticket 482?",
        retriever=forbidden,
        memory_generator=forbidden,
        incident_lookup=incident_lookup,
        memory_evaluator=forbidden,
        user={"role": "manager"},
    )

    assert result.status == "ok"
    assert "memory_eval" not in trace.node_order
    assert result.memory_proposal is None


def test_tool_statement_about_a_strike_is_evaluated_once(tmp_path):
    calls = {"n": 0}

    def incident_lookup(payload):
        return IncidentLookupOutput(
            ok=True, found=True, incidents=[incident_record()]
        )

    def memory_evaluator(**kwargs):
        calls["n"] += 1
        return EvaluationOutcome(proposal=ops_proposal())

    result, trace = run_traced(
        tmp_path,
        STRIKE_MESSAGE,
        retriever=forbidden,
        memory_generator=forbidden,
        incident_lookup=incident_lookup,
        memory_evaluator=memory_evaluator,
        user={"role": "manager"},
    )

    assert result.status == "ok"
    assert calls["n"] == 1
    assert trace.node_order == [
        "receive_question",
        "classify",
        "tool_incident",
        "answer_from_tool",
        "memory_eval",
    ]
    assert result.memory_proposal is not None
    assert result.memory_proposal["memory_type"] == "operational_context"
    assert node_event(trace, "memory_eval").output["memory_proposal"]


def test_no_context_answers_from_approved_memory_without_llm(tmp_path):
    memory_context = [
        {
            "id": "e1",
            "memory_type": "carrier_rule",
            "scope_label": "SEUR · ES · zona rural",
            "fact": (
                "SEUR ya no cubre la zona rural de Zaragoza; usar el "
                "carrier local."
            ),
            "created_at": "2026-11-14",
            "review_at": "2027-02-12",
        }
    ]
    result, trace = run_traced(
        tmp_path,
        "¿Qué carrier usamos para la zona rural de Zaragoza?",
        retriever=lambda question: [],
        generator=forbidden,
        memory_context=memory_context,
    )

    assert result.status == "ok"
    assert "SEUR ya no cubre" in result.answer
    assert result.memory_used is True
    assert trace.sources_used == ["rag", "memory"]
    assert "generate" not in trace.node_order


def test_generation_injects_the_bounded_memory_block(tmp_path):
    captured = {}

    def memory_generator(question, context, memory_context):
        captured["memory"] = memory_context
        return GenerationOutcome(answer="Respuesta", proposal=None)

    memory_context = [
        {
            "id": "e1",
            "memory_type": "carrier_rule",
            "scope_label": "SEUR · ES · zona rural",
            "fact": "SEUR ya no cubre la zona rural de Zaragoza.",
            "created_at": "2026-11-14",
        }
    ]
    run_traced(
        tmp_path,
        "¿Qué carrier usamos para la zona rural de Zaragoza?",
        retriever=lambda question: CHUNKS,
        memory_generator=memory_generator,
        memory_context=memory_context,
    )
    assert captured["memory"] == memory_context


def test_generation_trace_marks_memory_when_the_answer_uses_it(tmp_path):
    memory_context = [
        {
            "id": "e1",
            "memory_type": "carrier_rule",
            "scope_label": "SEUR · ES · zona rural",
            "fact": (
                "SEUR ya no cubre la zona rural de Zaragoza; usar el carrier "
                "local."
            ),
            "created_at": "2026-11-14",
        }
    ]

    def memory_generator(question, context, memory_context):
        return GenerationOutcome(
            answer=(
                "SEUR ya no cubre la zona rural de Zaragoza; hay que usar el "
                "carrier local."
            ),
            proposal=None,
        )

    result, trace = run_traced(
        tmp_path,
        "¿Qué carrier usamos para la zona rural de Zaragoza?",
        retriever=lambda question: CHUNKS,
        memory_generator=memory_generator,
        memory_context=memory_context,
    )
    assert result.memory_used is True
    assert trace.sources_used == ["rag", "memory"]


def test_trace_redacts_pii_in_question_answer_and_events(tmp_path):
    question = "La entrega es en Calle Mayor 12, piso 3. ¿Qué carrier usamos?"
    answer = "La entrega es en Calle Mayor 12, piso 3."

    result, trace = run_traced(
        tmp_path,
        question,
        retriever=lambda question: CHUNKS,
        generator=lambda question, context: answer,
    )
    raw = Path(result.trace_path).read_text(encoding="utf-8")
    assert "Calle Mayor" not in raw
    assert "Calle Mayor" not in trace.question
    assert "Calle Mayor" not in trace.answer
    assert "[REDACTED_ADDRESS]" in raw
    generate_event = node_event(trace, "generate")
    assert "Calle Mayor" not in generate_event.output["answer"]


# --- Generación con JSON estructurado ---------------------------------------


def _llm(payload, raw="{}"):
    def call(messages, **kwargs):
        return payload, raw

    return call


def _generation_payload(proposal: dict | None) -> dict:
    return {"respuesta": "Respuesta visible", "propuesta_memoria": proposal}


def test_generate_with_memory_parses_and_validates_a_proposal():
    proposal = carrier_proposal().model_dump()
    outcome = generate_with_memory(
        SEUR_MESSAGE,
        CHUNKS,
        [],
        llm=_llm(_generation_payload(proposal)),
    )
    assert outcome.answer == "Respuesta visible"
    assert outcome.proposal is not None
    assert outcome.proposal.scope.key == "carrier:SEUR:ES:rural"
    assert outcome.validation_error is None


def test_generate_with_memory_discards_a_non_grounded_quote():
    proposal = carrier_proposal().model_dump()
    proposal["source_quote"] = "una cita que no está en el mensaje"
    outcome = generate_with_memory(
        SEUR_MESSAGE,
        CHUNKS,
        [],
        llm=_llm(_generation_payload(proposal)),
    )
    assert outcome.answer == "Respuesta visible"
    assert outcome.proposal is None
    assert outcome.validation_error == "not_grounded"


def test_generate_with_memory_falls_back_to_plain_text():
    outcome = generate_with_memory(
        "¿Cuál es el SLA?",
        CHUNKS,
        [],
        llm=_llm(None, raw="El SLA es de 3 a 5 días hábiles."),
    )
    assert outcome.answer == "El SLA es de 3 a 5 días hábiles."
    assert outcome.proposal is None
    assert outcome.json_ok is False
    assert outcome.validation_error == "json_parse_error"


def test_generate_with_memory_does_not_show_broken_json_to_the_user():
    outcome = generate_with_memory(
        "¿Cuál es el SLA?",
        CHUNKS,
        [],
        llm=_llm(None, raw='{"respuesta": "roto"'),
    )
    assert "No pude completar la respuesta" in outcome.answer
    assert outcome.json_ok is False


def test_generate_with_memory_requires_context():
    outcome = generate_with_memory(SEUR_MESSAGE, [], [])
    assert outcome.proposal is None
    assert "No tengo información suficiente" in outcome.answer


def test_generate_with_memory_strips_a_trailing_confirmation_question():
    outcome = generate_with_memory(
        SEUR_MESSAGE,
        CHUNKS,
        [],
        llm=_llm(
            {
                "respuesta": (
                    "Entendido: SEUR ya no cubre la zona rural. "
                    "¿Quieres que proponga registrar este cambio como memoria "
                    "para futuras conversaciones?"
                ),
                "propuesta_memoria": None,
            }
        ),
    )
    assert outcome.answer == "Entendido: SEUR ya no cubre la zona rural."
    assert "¿Quieres" not in outcome.answer


def test_structured_output_is_valid_json_in_the_prompt():
    from services.api.app.agent.memory.prompts import (
        build_generation_messages,
    )

    messages = build_generation_messages(SEUR_MESSAGE, CHUNKS, [])
    assert "propuesta_memoria" in messages[0]["content"]
    assert "cita_origen" in messages[0]["content"]
    assert SEUR_MESSAGE in messages[1]["content"]
    # El esquema del prompt es JSON válido (sin las llaves dinámicas).
    schema = messages[0]["content"].split("ESQUEMA DE SALIDA")[1]
    assert "respuesta" in schema and "propuesta_memoria" in schema
