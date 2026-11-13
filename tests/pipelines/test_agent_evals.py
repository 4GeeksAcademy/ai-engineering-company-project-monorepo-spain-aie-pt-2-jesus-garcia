"""Evals del grafo del agente sobre traces estructurados.

Se ejecutan con un único comando:

    uv run pytest tests/pipelines/test_agent_evals.py -q

Los evals de enrutamiento ejecutan el grafo con dobles de prueba (sin red) y
verifican el **trace persistido**; el eval de anclaje lee traces reales
grabados con ``scripts/record_agent_traces.py`` y comprueba que la respuesta
sigue citando la base de conocimiento de TrackFlow.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from langgraph.graph import END, START, StateGraph

from data.pipelines import rag
from services.api.app.agent.graph import (
    AgentGraphConfigurationError,
    compile_agent_graph,
)
from services.api.app.agent.runner import get_run_state, run_agent
from services.api.app.agent.state import AgentState
from services.api.app.agent.tracing import AgentTrace

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent_traces"

CHUNKS: list[dict[str, Any]] = [
    {
        "company": "trackflow",
        "source_document": "sla-delivery",
        "section": "SLA de Entrega",
        "chunk_index": 0,
        "text": "El envío estándar dentro del mismo país tarda de 3 a 5 días hábiles.",
    },
    {
        "company": "trackflow",
        "source_document": "returns-policy",
        "section": "Política de Devoluciones",
        "chunk_index": 1,
        "text": "La ventana de devolución estándar es de 30 días desde la entrega.",
    },
]


def flat(text: str) -> str:
    """Normaliza espacios para comparar fragmentos de la respuesta."""
    return re.sub(r"\s+", "", text or "").lower()


def run_traced(
    tmp_path: Path,
    question: str,
    *,
    retriever,
    generator,
) -> tuple[Any, AgentTrace, Any]:
    graph = compile_agent_graph(retriever=retriever, generator=generator)
    result = run_agent(question, graph=graph, trace_dir=tmp_path)
    trace = AgentTrace.load(result.trace_path)
    return result, trace, graph


def test_blank_question_routes_to_fail_without_retrieval_or_generation(tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("No debe ejecutarse retrieve ni generate con una pregunta vacía.")

    result, trace, _ = run_traced(
        tmp_path, "   ", retriever=forbidden, generator=forbidden
    )

    assert result.status == "invalid_question"
    assert trace.node_order == ["receive_question", "fail"]
    assert trace.retrieved_sources == []
    assert "retrieve" not in trace.node_order
    assert "generate" not in trace.node_order


def test_retrieve_runs_before_generate_and_passes_its_own_context(tmp_path):
    calls: dict[str, Any] = {"retrieve": 0, "generate": 0}

    def retriever(question: str) -> list[dict]:
        calls["retrieve"] += 1
        calls["question"] = question
        return CHUNKS

    def generator(question: str, context: list[dict]) -> str:
        calls["generate"] += 1
        calls["generator_question"] = question
        calls["context"] = context
        return "El envío estándar tarda de 3 a 5 días hábiles."

    result, trace, _ = run_traced(
        tmp_path, "  ¿Cuánto tarda un envío estándar?  ",
        retriever=retriever, generator=generator,
    )

    assert result.status == "ok"
    assert trace.node_order == ["receive_question", "retrieve", "generate"]
    assert calls["retrieve"] == 1
    assert calls["generate"] == 1
    assert calls["question"] == "¿Cuánto tarda un envío estándar?"
    assert calls["context"] == CHUNKS
    assert calls["generator_question"] == calls["question"]

    retrieve_event = trace.events[1]
    assert retrieve_event.output["context_count"] == len(CHUNKS)
    assert [source["source_document"] for source in trace.retrieved_sources] == [
        "sla-delivery",
        "returns-policy",
    ]
    assert trace.answer == "El envío estándar tarda de 3 a 5 días hábiles."


def test_empty_retrieval_routes_to_honest_answer_without_llm(tmp_path):
    def forbidden_generator(*args, **kwargs):
        pytest.fail("No debe generarse una respuesta sin contexto recuperado.")

    result, trace, _ = run_traced(
        tmp_path,
        "¿Cuánto cuesta el alquiler de un avión privado?",
        retriever=lambda question: [],
        generator=forbidden_generator,
    )

    assert result.status == "no_context"
    assert trace.node_order == ["receive_question", "retrieve", "no_context"]
    assert "generate" not in trace.node_order
    assert trace.retrieved_sources == []
    assert "No tengo información suficiente" in trace.answer
    assert trace.answer == rag.NO_CONTEXT_ANSWER


@pytest.mark.parametrize(
    ("fixture", "expected_document", "expected_answer"),
    [
        ("sla-standard", "sla-delivery", "3 a 5 días hábiles"),
        ("sla-peak-demand", "sla-delivery", "40%"),
        ("returns-international", "returns-policy", "gestión manual"),
        ("storage-discount-approval", "storage-pricing", "Miguel Torres"),
    ],
)
def test_answer_stays_anchored_in_the_knowledge_base(
    fixture: str,
    expected_document: str,
    expected_answer: str,
):
    trace = AgentTrace.load(FIXTURES / f"{fixture}.json")

    assert trace.status == "ok"
    assert trace.node_order == ["receive_question", "retrieve", "generate"]
    assert expected_document in {
        source.get("source_document") for source in trace.retrieved_sources
    }, f"El trace {fixture} no recuperó {expected_document}"
    assert flat(expected_answer) in flat(trace.answer), (
        f"La respuesta del trace {fixture} no cita {expected_answer!r}"
    )
    assert len(trace.checkpoints) == len(trace.events)


def test_checkpointing_records_every_transition(tmp_path):
    result, trace, graph = run_traced(
        tmp_path,
        "¿Cuánto tarda un envío estándar?",
        retriever=lambda question: CHUNKS,
        generator=lambda question, context: "Tarda de 3 a 5 días hábiles.",
    )

    assert len(trace.checkpoints) == len(trace.events) == 3
    assert len({record.checkpoint_id for record in trace.checkpoints}) == 3
    assert trace.checkpoints[0].next_nodes == ["retrieve"]
    assert trace.checkpoints[1].next_nodes == ["generate"]
    assert trace.checkpoints[-1].next_nodes == []

    state = get_run_state(result.run_id, graph=graph)
    assert state["values"]["answer"] == trace.answer
    assert state["values"]["status"] == "ok"
    snapshot = graph.get_state({"configurable": {"thread_id": result.run_id}})
    assert snapshot.values["answer"] == trace.answer


def test_compilation_rejects_a_disconnected_node():
    builder = StateGraph(AgentState)
    builder.add_node("receive_question", lambda state: {})
    builder.add_node("orphan", lambda state: {})
    builder.add_edge(START, "receive_question")
    builder.add_edge("receive_question", END)

    with pytest.raises(AgentGraphConfigurationError, match="orphan"):
        compile_agent_graph(builder)


def test_compilation_rejects_a_badly_typed_state():
    class FakeBuilder:
        state_schema = dict

        def compile(self, **kwargs):  # pragma: no cover - no debe invocarse
            raise AssertionError("No debe compilarse un estado mal tipado.")

    with pytest.raises(AgentGraphConfigurationError, match="TypedDict"):
        compile_agent_graph(FakeBuilder())
