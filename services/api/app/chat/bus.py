"""Pub/sub por sesión de chat.

El productor (la generación del agente) publica una vez en el canal
``chat.<session_id>`` y cada conexión WebSocket suscrita recibe su copia. Esto
desacopla ambos lados: el productor no conoce sockets y un cliente lento no
bloquea a los demás ni provoca una segunda llamada al agente.

La implementación es en memoria (un solo proceso), tal y como permite el
BRIEFING. La interfaz replica el contrato mínimo para sustituirla por Redis
pub/sub usando el mismo nombre de canal.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatEvent:
    """Evento nombrado listo para el wire WebSocket."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {"event": self.name, "data": dict(self.data)}


class ChatSubscription:
    """Cola de una conexión. ``push`` es seguro desde otros hilos."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[ChatEvent] = asyncio.Queue()
        self.closed = False

    def push(self, event: ChatEvent) -> None:
        if self.closed:
            return
        try:
            self._loop.call_soon_threadsafe(self._put, event)
        except RuntimeError:  # loop cerrado: la conexión ya se fue
            self.closed = True

    def _put(self, event: ChatEvent) -> None:
        if self.closed:
            return
        self._queue.put_nowait(event)

    async def get(self) -> ChatEvent:
        return await self._queue.get()

    def pending(self) -> int:
        return self._queue.qsize()

    def close(self) -> None:
        self.closed = True


class ChatEventBus:
    """Fan-out en memoria con un canal lógico por sesión."""

    def __init__(self) -> None:
        self._subs: dict[str, set[ChatSubscription]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def channel(session_id: str) -> str:
        return f"chat.{session_id}"

    async def subscribe(
        self,
        session_id: str,
        loop: asyncio.AbstractEventLoop,
    ) -> ChatSubscription:
        subscription = ChatSubscription(loop)
        with self._lock:
            self._subs.setdefault(session_id, set()).add(subscription)
        return subscription

    async def unsubscribe(
        self,
        session_id: str,
        subscription: ChatSubscription,
    ) -> None:
        with self._lock:
            subscribers = self._subs.get(session_id)
            if subscribers is not None:
                subscribers.discard(subscription)
                if not subscribers:
                    self._subs.pop(session_id, None)
        subscription.close()

    def publish(
        self,
        session_id: str,
        name: str,
        data: dict[str, Any],
    ) -> ChatEvent:
        event = ChatEvent(name=name, data=dict(data))
        with self._lock:
            subscribers = list(self._subs.get(session_id, ()))
        for subscription in subscribers:
            subscription.push(event)
        return event

    def subscriber_count(self, session_id: str) -> int:
        with self._lock:
            return len(self._subs.get(session_id, ()))

    def reset(self) -> None:
        """Solo para tests: cierra y limpia todas las suscripciones."""

        with self._lock:
            subscriptions = [
                subscription
                for subscribers in self._subs.values()
                for subscription in subscribers
            ]
            self._subs.clear()
        for subscription in subscriptions:
            subscription.close()


_bus: ChatEventBus | None = None
_bus_lock = threading.Lock()


def get_chat_bus() -> ChatEventBus:
    global _bus
    with _bus_lock:
        if _bus is None:
            _bus = ChatEventBus()
        return _bus


def reset_chat_bus() -> None:
    global _bus
    with _bus_lock:
        current = _bus
        _bus = None
    if current is not None:
        current.reset()


__all__ = [
    "ChatEvent",
    "ChatEventBus",
    "ChatSubscription",
    "get_chat_bus",
    "reset_chat_bus",
]
