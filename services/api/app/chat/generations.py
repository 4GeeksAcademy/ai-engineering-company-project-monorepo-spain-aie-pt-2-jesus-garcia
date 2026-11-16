"""Registro de la generación activa por sesión y su aborto cooperativo.

Solo puede haber **una** generación por sesión: la primera conexión que envía
``user_message`` la arranca y las demás se limitan a consumir sus eventos. El
lock de emisión garantiza el orden estricto del wire:

    token_chunk* → interrupt_requested → generation_interrupted

Ningún token de la generación antigua puede publicarse después de la
interrupción, porque emisión y aborto compiten por el mismo lock.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

PublishToken = Callable[["ActiveGeneration", int, str], None]
PublishInterrupt = Callable[["ActiveGeneration", str | None], None]
PublishClose = Callable[["ActiveGeneration", bool, int, str, dict[str, Any]], None]


@dataclass
class ActiveGeneration:
    session_id: str
    message_id: str
    run_id: str
    user_id: str
    abort: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    sequence: int = 0
    text: str = ""
    finalized: bool = False
    task: Any | None = None

    def emit_token(
        self,
        chunk: str,
        publish: PublishToken,
    ) -> int | None:
        """Publica un token si la generación sigue viva; devuelve su secuencia."""

        if not chunk:
            return None
        with self.lock:
            if self.abort.is_set() or self.finalized:
                return None
            self.sequence += 1
            self.text += chunk
            sequence = self.sequence
            publish(self, sequence, chunk)
            return sequence

    def request_abort(
        self,
        publish: PublishInterrupt,
        new_input: str | None,
    ) -> bool:
        """Activa el aborto y publica ``interrupt_requested`` bajo el lock."""

        with self.lock:
            if self.abort.is_set() or self.finalized:
                return False
            self.abort.set()
            publish(self, new_input)
            return True

    def snapshot(self) -> tuple[int, str]:
        with self.lock:
            return self.sequence, self.text

    def is_aborted(self) -> bool:
        with self.lock:
            return self.abort.is_set()

    def close(
        self,
        publish: PublishClose,
        *,
        completed_text: str,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Cierra la generación una sola vez y publica el evento final.

        Si el aborto ganó la carrera, publica ``generation_interrupted`` con el
        texto parcial. Si no, ``generation_completed`` con el texto final.
        """

        with self.lock:
            if self.finalized:
                return False
            self.finalized = True
            aborted = self.abort.is_set()
            self.abort.set()
            sequence = self.sequence
            text = self.text if aborted else completed_text
            publish(self, aborted, sequence, text, dict(meta or {}))
            return True


class GenerationRegistry:
    """Mapa ``session_id -> ActiveGeneration`` seguro entre hilos y loop."""

    def __init__(self) -> None:
        self._items: dict[str, ActiveGeneration] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> ActiveGeneration | None:
        with self._lock:
            return self._items.get(session_id)

    def try_register(self, generation: ActiveGeneration) -> bool:
        with self._lock:
            if generation.session_id in self._items:
                return False
            self._items[generation.session_id] = generation
            return True

    def release(self, generation: ActiveGeneration) -> None:
        with self._lock:
            if self._items.get(generation.session_id) is generation:
                self._items.pop(generation.session_id, None)

    def reset(self) -> None:
        with self._lock:
            self._items.clear()


__all__ = [
    "ActiveGeneration",
    "GenerationRegistry",
    "PublishClose",
    "PublishInterrupt",
    "PublishToken",
]
