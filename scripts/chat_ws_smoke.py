#!/usr/bin/env python3
"""Verificación E2E del WebSocket de chat.

Escenarios:

1. Handshake con JWT y ``session_id`` existente.
2. Streaming token a token.
3. Interrupción a mitad: ``generation_interrupted`` con el parcial, sin más
   ``token_chunk`` de la generación antigua y un turno nuevo para ``new_input``.
4. Reconexión con el mismo ``session_id``: snapshot con el historial.

Uso (con el stack Docker levantado):

    services/api/venv/bin/python scripts/chat_ws_smoke.py

Variables: CHAT_SMOKE_API_URL, CHAT_SMOKE_EMAIL, CHAT_SMOKE_PASSWORD.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from websockets.sync.client import connect

API_URL = os.getenv("CHAT_SMOKE_API_URL", "http://localhost:8000").rstrip("/")
EMAIL = os.getenv("CHAT_SMOKE_EMAIL", "admin@trackflow.com")
PASSWORD = os.getenv("CHAT_SMOKE_PASSWORD", "admin123")
FIRST_QUESTION = "¿Cuánto tarda una entrega estándar en España?"
NEW_INPUT = "espera, quiero hacer una devolución"


def api(path: str, *, token: str | None = None, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=data,
        method="POST" if data is not None else "GET",
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode() or "null")


def ws_url(session_id: str, token: str) -> str:
    base = API_URL.replace("https://", "wss://").replace("http://", "ws://")
    return f"{base}/chat/ws?session_id={session_id}&token={token}"


def recv_until(socket, predicate, *, limit: int = 3_000) -> list[dict]:
    events: list[dict] = []
    for _ in range(limit):
        event = json.loads(socket.recv(timeout=120))
        events.append(event)
        if predicate(event):
            return events
    raise AssertionError("No se alcanzó el evento esperado.")


def main() -> int:
    login = api("/api/auth/login", payload={"email": EMAIL, "password": PASSWORD})
    token = login["access_token"]
    session = api("/chat/sessions", token=token, payload={})
    session_id = session["session_id"]
    print(f"session_id={session_id}")

    url = ws_url(session_id, token)

    # --- Escenario 1 + 2: snapshot y streaming -----------------------------
    with connect(url) as socket:
        snapshot = json.loads(socket.recv())
        assert snapshot["event"] == "session_snapshot", snapshot
        assert snapshot["data"]["session_id"] == session_id
        print("ok snapshot inicial")

        socket.send(
            json.dumps(
                {
                    "event": "user_message",
                    "data": {"session_id": session_id, "text": FIRST_QUESTION},
                }
            )
        )

        events: list[dict] = []
        old_message_id = None
        while old_message_id is None:
            event = json.loads(socket.recv(timeout=120))
            events.append(event)
            if event["event"] == "token_chunk":
                old_message_id = event["data"]["message_id"]
                print(f"token seq={event['data']['sequence']}…")
                break

        # --- Escenario 3: interrupción ------------------------------------
        socket.send(
            json.dumps(
                {
                    "event": "interrupt_requested",
                    "data": {"session_id": session_id, "new_input": NEW_INPUT},
                }
            )
        )
        events += recv_until(
            socket,
            lambda event: event["event"] == "generation_completed"
            and event["data"]["message_id"] != old_message_id,
        )

    names = [event["event"] for event in events]
    assert "interrupt_requested" in names, names
    interrupted = next(
        event
        for event in events
        if event["event"] == "generation_interrupted"
        and event["data"]["message_id"] == old_message_id
    )
    partial = interrupted["data"]["text"]
    assert partial, "El parcial interrumpido no conserva tokens"
    print(f"ok interrupción: mensaje={old_message_id} parcial={partial!r}")

    interrupted_index = next(
        index
        for index, event in enumerate(events)
        if event["event"] == "generation_interrupted"
        and event["data"]["message_id"] == old_message_id
    )
    late_tokens = [
        event
        for event in events[interrupted_index + 1:]
        if event["event"] == "token_chunk"
        and event["data"]["message_id"] == old_message_id
    ]
    assert not late_tokens, f"Salieron tokens después del aborto: {late_tokens}"

    completed = events[-1]["data"]
    assert completed["message_id"] != old_message_id
    assert completed["text"], "El turno nuevo no trajo respuesta"
    print(
        "ok turno nuevo: "
        f"mensaje={completed['message_id']} texto={completed['text'][:80]!r}"
    )

    history = api(f"/chat/sessions/{session_id}/messages", token=token)
    interrupted_row = next(
        item for item in history if item["message_id"] == old_message_id
    )
    assert interrupted_row["status"] == "interrupted"
    assert interrupted_row["text"] == partial
    assert any(
        item["role"] == "user" and item["text"] == NEW_INPUT for item in history
    )
    assert any(
        item["message_id"] == completed["message_id"]
        and item["status"] == "completed"
        for item in history
    )
    print("ok historial: parcial inmutable + turno nuevo persistido")

    # --- Escenario 4: reconexión ------------------------------------------
    with connect(url) as socket:
        snapshot = json.loads(socket.recv())
        assert snapshot["event"] == "session_snapshot"
        messages = snapshot["data"]["messages"]
        assert messages, "El snapshot de reconexión está vacío"
        assert any(
            item["message_id"] == old_message_id
            and item["status"] == "interrupted"
            for item in messages
        )
        print(f"ok reconexión: {len(messages)} mensajes restaurados")

    print("OK chat WebSocket E2E")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, urllib.error.URLError, OSError) as exc:
        print(f"FALLO: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
