"""Contexto de streaming de una corrida del agente.

El canal WebSocket necesita dos cosas que una llamada síncrona no ofrece:

* recibir los tokens del modelo mientras se generan, y
* poder **abortar** la generación a mitad de respuesta.

Ambas viajan por ``ContextVar``: ``run_agent`` las enlaza antes de ejecutar el
grafo y los nodos (que se compilan una sola vez) las leen en tiempo de
ejecución. No se guardan en el estado del grafo porque un evento de
``threading`` no es serializable por el checkpointer.
"""

from __future__ import annotations

import threading
from contextvars import ContextVar, Token
from typing import Callable

TokenSink = Callable[[str], None]

_abort: ContextVar[threading.Event | None] = ContextVar(
    "agent_abort_event", default=None
)
_streaming: ContextVar[bool] = ContextVar("agent_streaming_enabled", default=False)


class GenerationAborted(RuntimeError):
    """La generación se detuvo porque el cliente pidió interrumpirla."""


def current_abort() -> threading.Event | None:
    """Evento de aborto de la corrida actual (``None`` fuera de una corrida)."""

    return _abort.get()


def abort_requested() -> bool:
    event = _abort.get()
    return bool(event is not None and event.is_set())


def streaming_enabled() -> bool:
    """True solo cuando la corrida se abrió con un ``token_sink``."""

    return bool(_streaming.get())


def bind_run(
    *,
    abort: threading.Event | None,
    streaming: bool,
) -> tuple[Token, Token]:
    """Enlaza el contexto de la corrida; devolver los tokens para restaurarlo."""

    return _abort.set(abort), _streaming.set(streaming)


def reset_run(tokens: tuple[Token, Token]) -> None:
    abort_token, streaming_token = tokens
    _streaming.reset(streaming_token)
    _abort.reset(abort_token)


__all__ = [
    "GenerationAborted",
    "TokenSink",
    "abort_requested",
    "bind_run",
    "current_abort",
    "reset_run",
    "streaming_enabled",
]
