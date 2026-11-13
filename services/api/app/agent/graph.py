"""Construcción, validación estructural y compilación del grafo del agente.

El grafo se compila de forma explícita antes de cualquier ejecución: un nodo
huérfano, una arista hacia un nodo inexistente o un estado mal tipado hacen
fallar la compilación con :class:`AgentGraphConfigurationError` y un mensaje
que nombra el problema.
"""

from __future__ import annotations

from collections import deque
from functools import lru_cache
from typing import Any, is_typeddict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    Classifier,
    Generator,
    Retriever,
    answer_from_tool_node,
    fail_node,
    make_classify_node,
    make_generate_node,
    make_retrieve_node,
    make_tool_incident_node,
    make_tool_inventory_node,
    no_context_node,
    receive_question,
)
from .state import AgentState
from .tools import IncidentLookup, InventoryLookup

START_NODE = "__start__"
END_NODE = "__end__"


class AgentGraphConfigurationError(RuntimeError):
    """El grafo no cumple el contrato estructural mínimo."""


def route_after_receive(state: AgentState) -> str:
    """Pregunta vacía → error terminal; pregunta válida → clasificar."""
    return "fail" if state.get("status") == "invalid_question" else "classify"


def route_after_classify(state: AgentState) -> str:
    """Ruta decidida por el clasificador → tool, RAG o error terminal."""
    if state.get("status") == "error":
        return "fail"
    route = state.get("route")
    if route in ("incident", "incident+rag"):
        return "tool_incident"
    if route in ("inventory", "inventory+rag"):
        return "tool_inventory"
    if route == "rag":
        return "retrieve"
    return "fail"


def route_after_incident_tool(state: AgentState) -> str:
    """Tool de tickets: si la ruta es ``+rag``, continúa con la recuperación."""
    return "retrieve" if state.get("route") == "incident+rag" else "answer_from_tool"


def route_after_inventory_tool(state: AgentState) -> str:
    """Tool de inventario: si la ruta es ``+rag``, continúa con la recuperación."""
    return (
        "retrieve" if state.get("route") == "inventory+rag" else "answer_from_tool"
    )


def route_after_retrieve(state: AgentState) -> str:
    """Fallo → error; con contexto → generar; sin contexto → tool u honestidad."""
    if state.get("status") == "error":
        return "fail"
    if state.get("context"):
        return "generate"
    if state.get("tool_name"):
        return "answer_from_tool"
    return "no_context"


def route_after_generate(state: AgentState) -> str:
    """Generación correcta → fin; fallo → error terminal."""
    return "fail" if state.get("status") == "error" else "done"


def build_agent_graph(
    *,
    retriever: Retriever | None = None,
    generator: Generator | None = None,
    classifier: Classifier | None = None,
    incident_lookup: IncidentLookup | None = None,
    inventory_lookup: InventoryLookup | None = None,
) -> StateGraph:
    """Declara nodos y aristas condicionales sin compilar."""
    _validate_state_schema(AgentState)

    builder = StateGraph(AgentState)
    builder.add_node("receive_question", receive_question)
    builder.add_node("classify", make_classify_node(classifier))
    builder.add_node("tool_incident", make_tool_incident_node(incident_lookup))
    builder.add_node("tool_inventory", make_tool_inventory_node(inventory_lookup))
    builder.add_node("retrieve", make_retrieve_node(retriever))
    builder.add_node("generate", make_generate_node(generator))
    builder.add_node("answer_from_tool", answer_from_tool_node)
    builder.add_node("no_context", no_context_node)
    builder.add_node("fail", fail_node)

    builder.add_edge(START, "receive_question")
    builder.add_conditional_edges(
        "receive_question",
        route_after_receive,
        {"classify": "classify", "fail": "fail"},
    )
    builder.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "retrieve": "retrieve",
            "tool_incident": "tool_incident",
            "tool_inventory": "tool_inventory",
            "fail": "fail",
        },
    )
    builder.add_conditional_edges(
        "tool_incident",
        route_after_incident_tool,
        {"retrieve": "retrieve", "answer_from_tool": "answer_from_tool"},
    )
    builder.add_conditional_edges(
        "tool_inventory",
        route_after_inventory_tool,
        {"retrieve": "retrieve", "answer_from_tool": "answer_from_tool"},
    )
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {
            "generate": "generate",
            "answer_from_tool": "answer_from_tool",
            "no_context": "no_context",
            "fail": "fail",
        },
    )
    builder.add_conditional_edges(
        "generate",
        route_after_generate,
        {"done": END, "fail": "fail"},
    )
    builder.add_edge("answer_from_tool", END)
    builder.add_edge("no_context", END)
    builder.add_edge("fail", END)
    return builder


def compile_agent_graph(
    builder: StateGraph | None = None,
    *,
    retriever: Retriever | None = None,
    generator: Generator | None = None,
    classifier: Classifier | None = None,
    incident_lookup: IncidentLookup | None = None,
    inventory_lookup: InventoryLookup | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """Valida y compila el grafo. Falla antes de cualquier ``invoke``."""
    if builder is None:
        builder = build_agent_graph(
            retriever=retriever,
            generator=generator,
            classifier=classifier,
            incident_lookup=incident_lookup,
            inventory_lookup=inventory_lookup,
        )

    _validate_state_schema(getattr(builder, "state_schema", None))

    try:
        compiled = builder.compile(checkpointer=checkpointer or InMemorySaver())
    except AgentGraphConfigurationError:
        raise
    except Exception as exc:  # noqa: BLE001 - se re-envuelve con contexto
        raise AgentGraphConfigurationError(
            f"El grafo no se pudo compilar: {exc}"
        ) from exc

    _validate_compiled_graph(compiled)
    return compiled


@lru_cache(maxsize=1)
def get_agent_graph() -> Any:
    """Grafo compilado y reutilizado por la API (un único checkpointer)."""
    return compile_agent_graph()


def _validate_state_schema(schema: Any) -> None:
    if schema is None:
        raise AgentGraphConfigurationError(
            "El grafo no declara un estado (state_schema vacío)."
        )
    if not is_typeddict(schema):
        raise AgentGraphConfigurationError(
            "El estado del grafo debe ser un TypedDict; recibido: "
            f"{type(schema).__name__}."
        )


def _validate_compiled_graph(compiled: Any) -> None:
    """Comprueba alcanzabilidad, aristas y nodos terminales del grafo compilado."""
    drawable = compiled.get_graph()
    nodes = set(drawable.nodes)
    edges = list(drawable.edges)

    if START_NODE not in nodes:
        raise AgentGraphConfigurationError(
            "El grafo compilado no tiene nodo de entrada (START)."
        )

    targets = {edge.target for edge in edges}
    dangling = sorted(target for target in targets if target not in nodes)
    if dangling:
        raise AgentGraphConfigurationError(
            f"Hay aristas hacia nodos inexistentes: {dangling}."
        )

    outgoing: dict[str, set[str]] = {node: set() for node in nodes}
    for edge in edges:
        outgoing.setdefault(edge.source, set()).add(edge.target)

    if not outgoing.get(START_NODE):
        raise AgentGraphConfigurationError(
            "El grafo no tiene ninguna arista de salida desde START."
        )

    reachable = _reachable_from_start(outgoing)
    unreachable = sorted(node for node in nodes if node not in reachable)
    if unreachable:
        raise AgentGraphConfigurationError(
            f"Hay nodos sin conexión desde START: {unreachable}."
        )

    dead_ends = sorted(
        node
        for node in reachable
        if node != END_NODE and not outgoing.get(node)
    )
    if dead_ends:
        raise AgentGraphConfigurationError(
            f"Hay nodos sin conexión de salida: {dead_ends}."
        )


def _reachable_from_start(outgoing: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    queue: deque[str] = deque([START_NODE])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(sorted(outgoing.get(node, set()) - seen))
    return seen


def graph_node_order(compiled: Any) -> list[str]:
    """Nodos declarados (sin los centinelas de LangGraph), para introspección."""
    return [
        node
        for node in compiled.get_graph().nodes
        if node not in (START_NODE, END_NODE)
    ]


__all__ = [
    "AgentGraphConfigurationError",
    "build_agent_graph",
    "compile_agent_graph",
    "get_agent_graph",
    "graph_node_order",
    "route_after_classify",
    "route_after_generate",
    "route_after_incident_tool",
    "route_after_inventory_tool",
    "route_after_receive",
    "route_after_retrieve",
]
