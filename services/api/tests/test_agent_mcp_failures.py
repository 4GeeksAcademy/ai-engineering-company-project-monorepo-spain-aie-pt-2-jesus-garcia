"""Regresión de la migración del agente al MCP Server.

Comprueba que el grafo sigue enrutando igual (RAG / incidencias / inventario) y
que cualquier fallo del cliente MCP se convierte en un fallback honesto, no en
un error que rompa la corrida.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app.agent.graph import compile_agent_graph
from app.agent.runner import run_agent
from app.agent.tools import (
    IncidentLookupOutput,
    InventoryItem,
    InventoryLookupOutput,
    set_mcp_client_for_tests,
)

CONTEXT = [
    {
        "company": "trackflow",
        "source_document": "sla-delivery",
        "section": "SLA de Entrega",
        "chunk_index": 0,
        "text": "El envío estándar dentro del mismo país tarda de 3 a 5 días hábiles.",
    }
]


class FailingIncidentClient:
    def __init__(self, error: str) -> None:
        self.error = error
        self.calls = 0

    def lookup_incident(self, payload):
        self.calls += 1
        return IncidentLookupOutput(
            ok=False,
            found=False,
            error=self.error,
            message="No se pudo confirmar el ticket.",
        )

    def lookup_inventory(self, payload):
        raise AssertionError("No debía consultarse inventario")


class FailingInventoryClient:
    def __init__(self, error: str) -> None:
        self.error = error
        self.calls = 0

    def lookup_incident(self, payload):
        raise AssertionError("No debía consultarse incidencias")

    def lookup_inventory(self, payload):
        self.calls += 1
        return InventoryLookupOutput(
            ok=False,
            found=False,
            error=self.error,
            message="No se pudo confirmar el stock.",
        )


class WorkingClient:
    def __init__(self) -> None:
        self.incident_calls = 0
        self.inventory_calls = 0

    def lookup_incident(self, payload):
        self.incident_calls += 1
        from app.agent.tools import IncidentRecord

        return IncidentLookupOutput(
            ok=True,
            found=True,
            incidents=[
                IncidentRecord(
                    id="42",
                    title="Paquete extraviado",
                    origin="customer",
                    branch="la_warehouse",
                    category="lost_parcel",
                    status="in_progress",
                )
            ],
        )

    def lookup_inventory(self, payload):
        self.inventory_calls += 1
        return InventoryLookupOutput(
            ok=True,
            found=True,
            items=[
                InventoryItem(
                    id=1,
                    name="Classic White Sneaker - Size 42",
                    sku_code="CLT-SNK-W-42",
                    warehouse="los_angeles",
                    current_stock=47,
                    current_stock_by_warehouse={"los_angeles": 47, "zaragoza": 0},
                )
            ],
        )


class ExplodingClient:
    def lookup_incident(self, payload):
        raise AssertionError("El RAG no debe invocar el MCP")

    def lookup_inventory(self, payload):
        raise AssertionError("El RAG no debe invocar el MCP")


def graph(retriever=None, generator=None):
    return compile_agent_graph(
        retriever=retriever or (lambda question: []),
        generator=generator or (lambda question, context: "respuesta"),
    )


def run(
    question: str,
    *,
    client,
    tmp_path: Path,
    retriever=None,
    generator=None,
):
    set_mcp_client_for_tests(client)
    try:
        return run_agent(
            question,
            graph=graph(retriever=retriever, generator=generator),
            trace_dir=tmp_path,
            user={"role": "manager"},
        )
    finally:
        set_mcp_client_for_tests(None)


def test_mcp_unavailable_does_not_break_incident_run(tmp_path):
    client = FailingIncidentClient("unavailable")
    result = run("¿En qué estado está el ticket 42?", client=client, tmp_path=tmp_path)
    assert result.status == "ok"
    assert "No pude confirmar" in result.answer
    assert client.calls == 1


def test_mcp_timeout_returns_honest_fallback(tmp_path):
    client = FailingIncidentClient("timeout")
    result = run("¿En qué estado está el ticket 42?", client=client, tmp_path=tmp_path)
    assert result.status == "ok"
    assert "no respondió a tiempo" in result.answer


def test_mcp_forbidden_returns_permission_fallback(tmp_path):
    client = FailingIncidentClient("forbidden")
    result = run("¿En qué estado está el ticket 42?", client=client, tmp_path=tmp_path)
    assert result.status == "ok"
    assert "permisos" in result.answer


def test_mcp_inventory_failure_returns_honest_fallback(tmp_path):
    client = FailingInventoryClient("unavailable")
    result = run(
        "¿Tenemos stock de CLT-SNK-W-42?", client=client, tmp_path=tmp_path
    )
    assert result.status == "ok"
    assert "No pude confirmar el stock" in result.answer
    assert client.calls == 1


def test_incident_route_still_works_with_mcp_client(tmp_path):
    client = WorkingClient()
    result = run("¿En qué estado está el ticket 42?", client=client, tmp_path=tmp_path)
    assert result.status == "ok"
    assert "En curso" in result.answer
    assert client.incident_calls == 1
    assert client.inventory_calls == 0


def test_inventory_route_still_works_with_mcp_client(tmp_path):
    client = WorkingClient()
    result = run(
        "¿Tenemos stock de CLT-SNK-W-42?", client=client, tmp_path=tmp_path
    )
    assert result.status == "ok"
    assert "47" in result.answer
    assert client.inventory_calls == 1


def test_rag_route_does_not_invoke_mcp(tmp_path):
    result = run(
        "¿Cuál es el SLA de entrega?",
        client=ExplodingClient(),
        tmp_path=tmp_path,
        retriever=lambda question: CONTEXT,
        generator=lambda question, context: "El SLA es de 3 a 5 días hábiles.",
    )
    assert result.status == "ok"
    assert "3 a 5 días" in result.answer


def test_direct_agent_tools_are_not_importable():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.agent.tools.incidents")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.agent.tools.inventory")
