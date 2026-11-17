"""Contrato HTTP del endpoint de consulta RAG."""

from __future__ import annotations

from app.routes import knowledge
from data.process.rag_config import RagConfigurationError


def test_knowledge_query_requires_auth(client):
    response = client.post("/knowledge/query", json={"question": "¿SLA estándar?"})

    assert response.status_code in (401, 403)


def test_knowledge_query_returns_only_answer(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        knowledge,
        "query",
        lambda question: "El envío estándar tarda de 3 a 5 días hábiles.",
    )

    response = client.post(
        "/knowledge/query",
        json={"question": "¿Cuánto tarda un envío estándar?"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "El envío estándar tarda de 3 a 5 días hábiles."
    }


def test_knowledge_query_rejects_blank_question(client, auth_headers):
    response = client.post(
        "/knowledge/query",
        json={"question": "   "},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_knowledge_query_maps_configuration_error(client, auth_headers, monkeypatch):
    def raise_config_error(question: str) -> str:
        raise RagConfigurationError("falta LLM_API_KEY")

    monkeypatch.setattr(knowledge, "query", raise_config_error)

    response = client.post(
        "/knowledge/query",
        json={"question": "¿SLA estándar?"},
        headers=auth_headers,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "El asistente no está configurado. Contacta con el equipo técnico."
    )


def test_knowledge_query_maps_upstream_error(client, auth_headers, monkeypatch):
    def raise_upstream_error(question: str) -> str:
        raise RuntimeError("proveedor caído")

    monkeypatch.setattr(knowledge, "query", raise_upstream_error)

    response = client.post(
        "/knowledge/query",
        json={"question": "¿SLA estándar?"},
        headers=auth_headers,
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "No se pudo generar la respuesta. Inténtalo de nuevo."
    )
