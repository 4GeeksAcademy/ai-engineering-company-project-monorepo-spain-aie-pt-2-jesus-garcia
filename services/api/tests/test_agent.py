"""Contrato HTTP del endpoint del agente (sin ejecutar el grafo real)."""

from __future__ import annotations

from app.agent.runner import AgentResult, AgentRunError
from app.routes import agent as agent_route


def _result(**overrides) -> AgentResult:
    values = {
        "run_id": "run-test-1",
        "status": "ok",
        "answer": "El envío estándar tarda de 3 a 5 días hábiles.",
        "error": None,
        "trace_path": "/tmp/run-test-1.json",
    }
    values.update(overrides)
    return AgentResult(**values)


def test_agent_query_requires_auth(client):
    response = client.post("/agent/query", json={"question": "¿SLA estándar?"})

    assert response.status_code in (401, 403)


def test_agent_query_invokes_the_graph_and_returns_run_id(client, auth_headers, monkeypatch):
    calls: list[str] = []

    def fake_run_agent(question: str, **kwargs) -> AgentResult:
        calls.append(question)
        return _result()

    monkeypatch.setattr(agent_route, "run_agent", fake_run_agent)

    response = client.post(
        "/agent/query",
        json={"question": "¿Cuánto tarda un envío estándar?"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "El envío estándar tarda de 3 a 5 días hábiles.",
        "run_id": "run-test-1",
    }
    assert calls == ["¿Cuánto tarda un envío estándar?"]


def test_agent_query_maps_invalid_question_without_leaking_details(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        agent_route,
        "run_agent",
        lambda question, **kwargs: _result(
            status="invalid_question",
            answer="",
            error="La pregunta no puede estar vacía.",
        ),
    )

    response = client.post(
        "/agent/query",
        json={"question": "   "},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "La pregunta no puede estar vacía."}


def test_agent_query_returns_honest_answer_with_200_when_no_context(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        agent_route,
        "run_agent",
        lambda question, **kwargs: _result(
            status="no_context",
            answer="No tengo información suficiente en la base de conocimiento.",
        ),
    )

    response = client.post(
        "/agent/query",
        json={"question": "¿Cuánto cuesta un helicóptero?"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["answer"].startswith("No tengo información suficiente")


def test_agent_query_maps_graph_error_to_502(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        agent_route,
        "run_agent",
        lambda question, **kwargs: _result(
            status="error",
            answer="",
            error=agent_route.GENERIC_ERROR_DETAIL,
        ),
    )

    response = client.post(
        "/agent/query",
        json={"question": "¿SLA estándar?"},
        headers=auth_headers,
    )

    assert response.status_code == 502
    assert response.json() == {"detail": agent_route.GENERIC_ERROR_DETAIL}


def test_agent_query_maps_run_failure_to_502_without_stack_trace(client, auth_headers, monkeypatch):
    def boom(question: str, **kwargs) -> AgentResult:
        raise AgentRunError("detalle interno que no debe salir")

    monkeypatch.setattr(agent_route, "run_agent", boom)

    response = client.post(
        "/agent/query",
        json={"question": "¿SLA estándar?"},
        headers=auth_headers,
    )

    assert response.status_code == 502
    body = response.text
    assert agent_route.GENERIC_ERROR_DETAIL in body
    assert "detalle interno" not in body
    assert "Traceback" not in body


def _write_trace(directory, run_id: str) -> None:
    import json
    from pathlib import Path

    payload = {
        "run_id": run_id,
        "thread_id": run_id,
        "question": "¿SLA estándar?",
        "status": "ok",
        "answer": "de 3 a 5 días hábiles",
        "error": None,
        "started_at": "2026-11-17T10:00:00.000+00:00",
        "finished_at": "2026-11-17T10:00:01.000+00:00",
        "duration_ms": 1000.0,
        "events": [
            {
                "node": "classify",
                "input": {},
                "output": {"route": "rag"},
                "duration_ms": 1.0,
                "timestamp": "2026-11-17T10:00:00.100+00:00",
            },
            {
                "node": "retrieve",
                "input": {},
                "output": {"sources": []},
                "duration_ms": 2.0,
                "timestamp": "2026-11-17T10:00:00.200+00:00",
            },
        ],
        "checkpoints": [],
        "guard_events": [],
    }
    Path(directory).mkdir(parents=True, exist_ok=True)
    (Path(directory) / f"{run_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_agent_trace_returns_route_and_sources(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))
    _write_trace(tmp_path, "run-trace-1")

    response = client.get("/agent/traces/run-trace-1", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-trace-1"
    assert body["route"] == "rag"
    assert body["sources_used"] == ["rag"]


def test_agent_trace_missing_returns_404(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))

    response = client.get("/agent/traces/run-inexistente", headers=auth_headers)

    assert response.status_code == 404


def test_agent_trace_rejects_path_traversal(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))

    response = client.get("/agent/traces/..", headers=auth_headers)

    assert response.status_code == 404


def test_agent_trace_forbidden_for_normal_user(client, user_headers):
    response = client.get("/agent/traces/run-trace-1", headers=user_headers)

    assert response.status_code == 403
