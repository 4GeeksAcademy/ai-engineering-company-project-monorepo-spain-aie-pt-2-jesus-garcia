"""Evals del grafo del agente sobre traces estructurados.

Se ejecutan con un único comando:

    uv run pytest tests/pipelines/test_agent_evals.py -q

Los evals de enrutamiento ejecutan el grafo con dobles de prueba (sin red ni
base de datos) y verifican el **trace persistido**: qué fuente se usó (RAG,
tool o ambas), en qué orden y con qué resultado. El eval de anclaje lee traces
reales grabados con ``scripts/record_agent_traces.py``.
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
from services.api.app.agent.router import classify_question
from services.api.app.agent.runner import get_run_state, run_agent
from services.api.app.agent.state import AgentState
from services.api.app.agent.tools.contracts import (
    IncidentLookupOutput,
    IncidentRecord,
    InventoryItem,
    InventoryLookupOutput,
)
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


def node_event(trace: AgentTrace, node: str):
    for event in trace.events:
        if event.node == node:
            return event
    raise AssertionError(f"El trace no contiene el nodo {node}")


def forbidden(*args, **kwargs):
    pytest.fail("No debía ejecutarse esa fuente para esta pregunta.")


def incident_record(**overrides) -> IncidentRecord:
    values = {
        "id": "482",
        "title": "Paquete extraviado",
        "description": "El paquete no aparece en tránsito.",
        "description_excerpt": "El paquete no aparece en tránsito.",
        "origin": "customer",
        "branch": "la_warehouse",
        "category": "lost_parcel",
        "status": "in_progress",
        "created_at": "2026-11-01T10:00:00+00:00",
        "updated_at": "2026-11-02T10:00:00+00:00",
    }
    values.update(overrides)
    return IncidentRecord(**values)


def inventory_item(**overrides) -> InventoryItem:
    values = {
        "id": 1,
        "name": "Classic White Sneaker - Size 42",
        "sku_code": "CLT-SNK-W-42",
        "warehouse": "los_angeles",
        "current_stock": 47,
        "current_stock_by_warehouse": {"los_angeles": 47, "zaragoza": 0},
    }
    values.update(overrides)
    return InventoryItem(**values)


def run_traced(
    tmp_path: Path,
    question: str,
    *,
    retriever,
    generator,
    classifier=None,
    incident_lookup=None,
    inventory_lookup=None,
    user=None,
) -> tuple[Any, AgentTrace, Any]:
    graph = compile_agent_graph(
        retriever=retriever,
        generator=generator,
        classifier=classifier,
        incident_lookup=incident_lookup,
        inventory_lookup=inventory_lookup,
    )
    result = run_agent(question, graph=graph, trace_dir=tmp_path, user=user)
    trace = AgentTrace.load(result.trace_path)
    return result, trace, graph


def test_blank_question_routes_to_fail_without_retrieval_or_generation(tmp_path):
    result, trace, _ = run_traced(
        tmp_path, "   ", retriever=forbidden, generator=forbidden
    )

    assert result.status == "invalid_question"
    assert trace.node_order == ["receive_question", "fail"]
    assert trace.retrieved_sources == []
    assert trace.route == ""
    assert trace.sources_used == []
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
        tmp_path,
        "  ¿Cuánto tarda un envío estándar?  ",
        retriever=retriever,
        generator=generator,
    )

    assert result.status == "ok"
    assert trace.route == "rag"
    assert trace.sources_used == ["rag"]
    assert trace.node_order == [
        "receive_question",
        "classify",
        "retrieve",
        "generate",
    ]
    assert calls["retrieve"] == 1
    assert calls["generate"] == 1
    assert calls["question"] == "¿Cuánto tarda un envío estándar?"
    assert calls["context"] == CHUNKS
    assert calls["generator_question"] == calls["question"]

    retrieve_event = node_event(trace, "retrieve")
    assert retrieve_event.output["context_count"] == len(CHUNKS)
    assert [source["source_document"] for source in trace.retrieved_sources] == [
        "sla-delivery",
        "returns-policy",
    ]
    assert trace.answer == "El envío estándar tarda de 3 a 5 días hábiles."


def test_empty_retrieval_routes_to_honest_answer_without_llm(tmp_path):
    result, trace, _ = run_traced(
        tmp_path,
        "¿Cuánto cuesta el alquiler de un avión privado?",
        retriever=lambda question: [],
        generator=forbidden,
    )

    assert result.status == "no_context"
    assert trace.route == "rag"
    assert trace.sources_used == ["rag"]
    assert trace.node_order == [
        "receive_question",
        "classify",
        "retrieve",
        "no_context",
    ]
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
    assert trace.node_order in (
        ["receive_question", "retrieve", "generate"],
        ["receive_question", "classify", "retrieve", "generate"],
    )
    assert trace.sources_used == ["rag"]
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

    assert len(trace.checkpoints) == len(trace.events) == 4
    assert len({record.checkpoint_id for record in trace.checkpoints}) == 4
    assert trace.checkpoints[0].next_nodes == ["classify"]
    assert trace.checkpoints[1].next_nodes == ["retrieve"]
    assert trace.checkpoints[2].next_nodes == ["generate"]
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


# --- Evals de enrutamiento RAG / tools ---------------------------------------


def test_ticket_question_routes_to_incident_tool_without_rag(tmp_path):
    def incident_lookup(payload):
        assert payload.ticket_id == 482
        return IncidentLookupOutput(
            ok=True, found=True, incidents=[incident_record()]
        )

    result, trace, _ = run_traced(
        tmp_path,
        "¿En qué estado está el ticket 482?",
        retriever=forbidden,
        generator=forbidden,
        incident_lookup=incident_lookup,
        user={"role": "manager"},
    )

    assert result.status == "ok"
    assert trace.route == "incident"
    assert trace.sources_used == ["incident_tool"]
    assert trace.node_order == [
        "receive_question",
        "classify",
        "tool_incident",
        "answer_from_tool",
    ]
    assert "retrieve" not in trace.node_order
    assert "generate" not in trace.node_order
    assert "in_progress" in trace.answer
    assert "En curso" in trace.answer
    assert node_event(trace, "tool_incident").output["tool_status"] == "ok"


def test_policy_question_routes_to_rag_without_tools(tmp_path):
    result, trace, _ = run_traced(
        tmp_path,
        "¿Cuál es el SLA de un envío estándar?",
        retriever=lambda question: CHUNKS,
        generator=lambda question, context: (
            "El envío estándar tarda de 3 a 5 días hábiles."
        ),
        incident_lookup=forbidden,
        inventory_lookup=forbidden,
        user={"role": "manager"},
    )

    assert result.status == "ok"
    assert trace.route == "rag"
    assert trace.sources_used == ["rag"]
    assert trace.node_order == [
        "receive_question",
        "classify",
        "retrieve",
        "generate",
    ]
    assert "tool_incident" not in trace.node_order
    assert "tool_inventory" not in trace.node_order


def test_ticket_timeout_returns_honest_fallback_without_inventing_status(tmp_path):
    def incident_lookup(payload):
        return IncidentLookupOutput(
            ok=False,
            found=False,
            error="timeout",
            message="El gestor de incidencias no respondió a tiempo.",
        )

    result, trace, _ = run_traced(
        tmp_path,
        "¿En qué estado está el ticket 482?",
        retriever=forbidden,
        generator=forbidden,
        incident_lookup=incident_lookup,
        user={"role": "manager"},
    )

    assert result.status == "ok"
    assert trace.route == "incident"
    assert trace.sources_used == ["incident_tool"]
    assert trace.node_order == [
        "receive_question",
        "classify",
        "tool_incident",
        "answer_from_tool",
    ]
    assert "No pude confirmar" in trace.answer
    for invented_status in ("in_progress", "resolved", "discarded"):
        assert invented_status not in trace.answer.lower()
    tool_output = node_event(trace, "tool_incident").output
    assert tool_output["tool_status"] == "timeout"
    assert tool_output["fallback"] is True


def test_ticket_not_found_returns_honest_fallback(tmp_path):
    def incident_lookup(payload):
        return IncidentLookupOutput(
            ok=False,
            found=False,
            error="not_found",
            message="No existe la incidencia 999 en el gestor de incidencias.",
        )

    result, trace, _ = run_traced(
        tmp_path,
        "¿En qué estado está el ticket 999?",
        retriever=forbidden,
        generator=forbidden,
        incident_lookup=incident_lookup,
        user={"role": "manager"},
    )

    assert result.status == "ok"
    assert "No existe la incidencia 999" in trace.answer
    assert "in_progress" not in trace.answer.lower()
    assert node_event(trace, "tool_incident").output["tool_status"] == "not_found"


def test_ticket_plus_policy_routes_tool_then_rag(tmp_path):
    captured: dict[str, Any] = {}

    def incident_lookup(payload):
        assert payload.ticket_id == 482
        return IncidentLookupOutput(
            ok=True, found=True, incidents=[incident_record()]
        )

    def generator(question: str, context: list[dict]) -> str:
        captured["context"] = context
        return (
            "El ticket está en curso; según la política, la ventana de "
            "devolución es de 30 días desde la entrega."
        )

    result, trace, _ = run_traced(
        tmp_path,
        "¿Puedo devolver el paquete del ticket 482?",
        retriever=lambda question: CHUNKS,
        generator=generator,
        incident_lookup=incident_lookup,
        user={"role": "manager"},
    )

    assert result.status == "ok"
    assert trace.route == "incident+rag"
    assert trace.sources_used == ["incident_tool", "rag"]
    assert trace.node_order == [
        "receive_question",
        "classify",
        "tool_incident",
        "retrieve",
        "generate",
    ]
    assert any(
        item.get("source_document") == "incident-manager"
        for item in captured["context"]
    )
    assert any(
        item.get("source_document") == "sla-delivery"
        for item in captured["context"]
    )


def test_inventory_question_routes_to_inventory_tool(tmp_path):
    def inventory_lookup(payload):
        assert payload.sku_code == "CLT-SNK-W-42"
        return InventoryLookupOutput(
            ok=True, found=True, items=[inventory_item()]
        )

    result, trace, _ = run_traced(
        tmp_path,
        "¿Tenemos stock del SKU CLT-SNK-W-42?",
        retriever=forbidden,
        generator=forbidden,
        inventory_lookup=inventory_lookup,
        user={"role": "manager"},
    )

    assert result.status == "ok"
    assert trace.route == "inventory"
    assert trace.sources_used == ["inventory_tool"]
    assert trace.node_order == [
        "receive_question",
        "classify",
        "tool_inventory",
        "answer_from_tool",
    ]
    assert "47" in trace.answer
    assert "Los Ángeles" in trace.answer


def test_ticket_tool_applies_manager_permissions(tmp_path):
    result, trace, _ = run_traced(
        tmp_path,
        "¿En qué estado está el ticket 482?",
        retriever=forbidden,
        generator=forbidden,
        incident_lookup=forbidden,
        user={"role": "user"},
    )

    assert result.status == "ok"
    assert "permisos" in trace.answer.lower()
    assert node_event(trace, "tool_incident").output["tool_status"] == "forbidden"


@pytest.mark.parametrize(
    ("question", "expected_route", "ticket_id", "sku_code"),
    [
        ("¿En qué estado está el ticket 482?", "incident", 482, None),
        ("¿Cuál es el SLA de un envío estándar?", "rag", None, None),
        (
            "¿Tenemos stock del SKU CLT-SNK-W-42?",
            "inventory",
            None,
            "CLT-SNK-W-42",
        ),
        (
            "¿Puedo devolver el paquete del ticket 482?",
            "incident+rag",
            482,
            None,
        ),
        ("¿Hay stock de zapatillas blancas?", "inventory", None, None),
        ("¿Qué tickets están abiertos?", "incident", None, None),
    ],
)
def test_classifier_routes_questions_automatically(
    question: str,
    expected_route: str,
    ticket_id: int | None,
    sku_code: str | None,
):
    decision = classify_question(question)

    assert decision.route == expected_route
    assert decision.ticket_id == ticket_id
    assert decision.sku_code == sku_code
    if question == "¿Qué tickets están abiertos?":
        assert decision.filters.get("status") == "open"
