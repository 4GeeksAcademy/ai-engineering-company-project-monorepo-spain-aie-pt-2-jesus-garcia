"""Contrato nombrado de eventos y semántica de cierre de la generación."""

from __future__ import annotations

from app.chat import events
from app.chat.generations import ActiveGeneration


def _generation() -> ActiveGeneration:
    return ActiveGeneration(
        session_id="chat_0219",
        message_id="msg_0449",
        run_id="run-1",
        user_id="user-1",
    )


def test_canonical_event_names() -> None:
    assert set(events.EVENT_NAMES) == {
        "token_chunk",
        "interrupt_requested",
        "generation_interrupted",
        "generation_completed",
        "session_snapshot",
        "user_message",
        "generation_started",
        "error",
    }
    # No se mezclan los eventos RFP de la Parte 1.
    for rfp_event in ("rfp_ticket_created", "sla_threshold_alert"):
        assert rfp_event not in events.EVENT_NAMES


def test_token_chunk_payload_has_briefing_fields() -> None:
    generation = _generation()
    published: list[tuple[int, str]] = []

    def publish(gen, sequence, chunk):
        published.append((sequence, chunk))

    assert generation.emit_token("Tu", publish) == 1
    assert generation.emit_token(" pedido", publish) == 2
    assert published == [(1, "Tu"), (2, " pedido")]
    assert generation.snapshot() == (2, "Tu pedido")


def test_interrupt_then_no_more_tokens_and_interrupted_payload() -> None:
    generation = _generation()
    tokens: list[str] = []
    interrupts: list[str | None] = []
    closed: list[tuple[bool, int, str, dict]] = []

    generation.emit_token("Hola ", lambda gen, seq, chunk: tokens.append(chunk))
    changed = generation.request_abort(
        lambda gen, new_input: interrupts.append(new_input),
        "espera, quiero devolverlo",
    )
    assert changed
    assert interrupts == ["espera, quiero devolverlo"]

    # Ningún token puede publicarse después del aborto.
    assert generation.emit_token("esto no debe salir", lambda *_: tokens.append("X")) is None

    generation.close(
        lambda gen, aborted, seq, text, meta: closed.append(
            (aborted, seq, text, meta)
        ),
        completed_text="texto completo que no llegó",
    )
    assert tokens == ["Hola "]
    assert closed == [(True, 1, "Hola ", {})]
    # Un cierre tardío del productor no duplica el evento.
    assert not generation.close(
        lambda *_: closed.append((False, 0, "", {})),
        completed_text="tarde",
    )


def test_completion_payload_is_new_turn_not_overwrite() -> None:
    generation = _generation()
    closed: list[tuple[bool, int, str, dict]] = []
    generation.emit_token("Nueva respuesta", lambda gen, seq, chunk: None)
    generation.close(
        lambda gen, aborted, seq, text, meta: closed.append(
            (aborted, seq, text, meta)
        ),
        completed_text="Nueva respuesta completa",
        meta={"status": "ok", "blocked": False},
    )
    assert closed == [
        (False, 1, "Nueva respuesta completa", {"status": "ok", "blocked": False})
    ]
