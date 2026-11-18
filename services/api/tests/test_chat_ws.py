"""Contrato WebSocket del chat: auth, streaming, aborto y rehidratación."""

from __future__ import annotations

import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.agent.memory.service import ChatResult
from app.agent.streaming import GenerationAborted
from app.chat.service import ChatService, set_chat_service

pytestmark = pytest.mark.usefixtures("client")


class FakeRunner:
    """Productor determinista: no toca LLM, Qdrant ni red."""

    def __init__(self, *, filler: int = 0, delay: float = 0.0) -> None:
        self.filler = filler
        self.delay = delay
        self.calls = 0
        self.seen_history: list[list[dict]] = []

    def __call__(
        self,
        question: str,
        *,
        user,
        session_id: str,
        conversation_history: list[dict],
        on_token,
        abort,
    ) -> ChatResult:
        self.calls += 1
        self.seen_history.append(list(conversation_history))
        target = f"respuesta a {question}"
        visible: list[str] = []

        def emit(text: str) -> None:
            if abort is not None and abort.is_set():
                raise GenerationAborted()
            on_token(text)
            visible.append(text)
            if self.delay:
                time.sleep(self.delay)

        for word in target.split():
            emit(word + " ")

        filler = self.filler if self.calls == 1 else 0
        for index in range(filler):
            emit(f"relleno{index} ")

        return ChatResult(
            session_id=session_id,
            run_id=f"run-{self.calls}",
            answer="".join(visible).strip(),
            status="ok",
        )


def _create_session(client, auth_headers) -> str:
    created = client.post("/chat/sessions", headers=auth_headers, json={})
    assert created.status_code == 201, created.text
    return created.json()["session_id"]


def _next_event(websocket, *, skip_ping: bool = True) -> dict:
    while True:
        event = websocket.receive_json()
        if skip_ping and event.get("event") == "ping":
            continue
        return event


def _read_until(websocket, predicate, *, limit: int = 2_000) -> list[dict]:
    events: list[dict] = []
    for _ in range(limit):
        event = _next_event(websocket)
        events.append(event)
        if predicate(event):
            return events
    raise AssertionError("No se alcanzó el evento esperado")


def _service(runner: FakeRunner) -> ChatService:
    service = ChatService(runner=runner)
    set_chat_service(service)
    return service


def test_websocket_rejects_missing_or_invalid_token(client) -> None:
    created = client.post(
        "/chat/sessions",
        headers={"Authorization": "Bearer invalid"},
        json={},
    )
    assert created.status_code == 401

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/chat/ws?session_id=chat_missing") as ws:
            ws.receive_json()


def test_websocket_streams_tokens_and_completes(client, auth_headers) -> None:
    _service(FakeRunner())
    session_id = _create_session(client, auth_headers)

    with client.websocket_connect(
        f"/chat/ws?token={auth_headers['Authorization'].split(' ', 1)[1]}"
        f"&session_id={session_id}"
    ) as ws:
        snapshot = _next_event(ws)
        assert snapshot["event"] == "session_snapshot"
        assert snapshot["data"]["session_id"] == session_id
        assert snapshot["data"]["thread_id"] == session_id
        assert snapshot["data"]["agent_id"] == "first_line_cx"
        assert snapshot["data"]["messages"] == []

        ws.send_json(
            {
                "event": "user_message",
                "data": {"session_id": session_id, "text": "¿Dónde está mi pedido?"},
            }
        )

        events = _read_until(
            ws,
            lambda event: event.get("event") == "generation_completed",
        )

    names = [event["event"] for event in events]
    assert names[0] == "user_message"
    assert "generation_started" in names
    assert names[-1] == "generation_completed"

    chunks = [event for event in events if event["event"] == "token_chunk"]
    assert len(chunks) > 1
    assert [chunk["data"]["sequence"] for chunk in chunks] == list(
        range(1, len(chunks) + 1)
    )
    message_ids = {chunk["data"]["message_id"] for chunk in chunks}
    assert len(message_ids) == 1
    assert "token" in chunks[0]["data"]

    completed = events[-1]["data"]
    assert completed["message_id"] in message_ids
    assert "respuesta a ¿Dónde está mi pedido?" in completed["text"]

    history = client.get(
        f"/chat/sessions/{session_id}/messages",
        headers=auth_headers,
    ).json()
    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[1]["status"] == "completed"


def test_interrupt_stops_tokens_preserves_partial_and_starts_new_turn(
    client, auth_headers
) -> None:
    runner = FakeRunner(filler=200, delay=0.01)
    _service(runner)
    session_id = _create_session(client, auth_headers)

    with client.websocket_connect(
        f"/chat/ws?token={auth_headers['Authorization'].split(' ', 1)[1]}"
        f"&session_id={session_id}"
    ) as ws:
        _next_event(ws)  # snapshot
        ws.send_json(
            {
                "event": "user_message",
                "data": {"session_id": session_id, "text": "rastrea mi pedido"},
            }
        )

        # Consumir hasta tener al menos 3 tokens de la primera generación.
        seen_chunks = 0
        old_message_id = None
        while seen_chunks < 3:
            event = _next_event(ws)
            if event["event"] == "token_chunk":
                seen_chunks += 1
                old_message_id = event["data"]["message_id"]
        assert old_message_id

        ws.send_json(
            {
                "event": "interrupt_requested",
                "data": {
                    "session_id": session_id,
                    "new_input": "espera, quiero hacer una devolución",
                },
            }
        )

        events = _read_until(
            ws,
            lambda event: event.get("event") == "generation_completed",
        )

    names = [event["event"] for event in events]
    interrupt_index = names.index("interrupt_requested")
    interrupted_index = names.index("generation_interrupted")
    assert interrupt_index < interrupted_index

    interrupt = events[interrupt_index]["data"]
    assert interrupt["message_id"] == old_message_id
    assert interrupt["new_input"] == "espera, quiero hacer una devolución"

    interrupted = events[interrupted_index]["data"]
    assert interrupted["message_id"] == old_message_id
    assert interrupted["status"] == "interrupted"
    assert interrupted["text"].startswith("respuesta a")
    partial_text = interrupted["text"]

    # Ningún token de la generación antigua después del cierre.
    old_tokens_after = [
        event
        for event in events[interrupted_index + 1:]
        if event["event"] == "token_chunk"
        and event["data"]["message_id"] == old_message_id
    ]
    assert old_tokens_after == []

    new_user = [
        event for event in events if event["event"] == "user_message"
    ][-1]["data"]
    assert new_user["text"] == "espera, quiero hacer una devolución"

    completed = events[-1]["data"]
    assert completed["message_id"] != old_message_id
    assert "quiero hacer una devolución" in completed["text"]

    # El parcial interrumpido se conserva tal cual en el historial.
    history = client.get(
        f"/chat/sessions/{session_id}/messages",
        headers=auth_headers,
    ).json()
    interrupted_row = next(
        item for item in history if item["message_id"] == old_message_id
    )
    assert interrupted_row["status"] == "interrupted"
    assert interrupted_row["text"] == partial_text
    assert [item["role"] for item in history] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_reconnect_same_session_restores_history(client, auth_headers) -> None:
    runner = FakeRunner(filler=120, delay=0.01)
    _service(runner)
    session_id = _create_session(client, auth_headers)
    token = auth_headers["Authorization"].split(" ", 1)[1]

    with client.websocket_connect(
        f"/chat/ws?token={token}&session_id={session_id}"
    ) as first:
        _next_event(first)  # snapshot vacío
        first.send_json(
            {
                "event": "user_message",
                "data": {"session_id": session_id, "text": "estado del envío"},
            }
        )
        chunks = 0
        while chunks < 2:
            event = _next_event(first)
            if event["event"] == "token_chunk":
                chunks += 1

    # Reconexión con el MISMO session_id: snapshot con historial, no chat vacío.
    with client.websocket_connect(
        f"/chat/ws?token={token}&session_id={session_id}"
    ) as second:
        snapshot = _next_event(second)
        assert snapshot["event"] == "session_snapshot"
        data = snapshot["data"]
        assert data["session_id"] == session_id
        assert data["messages"]
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["text"] == "estado del envío"
        assert data["messages"][1]["role"] == "assistant"
        assert data["messages"][1]["status"] in ("streaming", "interrupted")
        if data["active_generation"] is not None:
            assert data["active_generation"]["text"].startswith("respuesta a")

        events = _read_until(
            second,
            lambda event: event.get("event") == "generation_completed",
        )
    completed = events[-1]["data"]
    assert completed["message_id"] == data["messages"][1]["message_id"]


def test_thread_id_alias_binds_to_session(client, auth_headers) -> None:
    _service(FakeRunner())
    session_id = _create_session(client, auth_headers)
    token = auth_headers["Authorization"].split(" ", 1)[1]
    with client.websocket_connect(
        f"/chat/ws?token={token}&thread_id={session_id}"
    ) as ws:
        snapshot = _next_event(ws)
        assert snapshot["data"]["thread_id"] == session_id
