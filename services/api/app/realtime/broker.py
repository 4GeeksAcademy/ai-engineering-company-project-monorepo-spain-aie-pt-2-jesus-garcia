"""Bus de eventos del canal en tiempo real.

Dos implementaciones con el mismo contrato:

* :class:`LocalBroker` — un único proceso (desarrollo y tests). El fan-out a
  cada conexión SSE se hace en memoria.
* :class:`RedisBroker` — pub/sub de Redis. El pipeline de RFPs corre en un
  worker Celery, que es otro proceso: sin Redis, el evento que nace en el
  worker no llega a la API.

Cada conexión SSE registra su propia :class:`Subscription` (cola acotada). Un
cliente lento no bloquea a los demás: se descarta el evento más antiguo y se
señala con ``stream_lagged`` para que el cliente reconcilie con un snapshot.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import os
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

CHANNEL = "realtime:events"
EVENT_SEQ_KEY = "realtime:events:seq"
RECENT_KEY = "realtime:events:recent"
RECENT_TTL_SECONDS = 3600

DEFAULT_QUEUE_SIZE = int(os.getenv("REALTIME_QUEUE_SIZE", "200"))
DEFAULT_REPLAY_LIMIT = int(os.getenv("REALTIME_REPLAY_LIMIT", "200"))


@dataclass(frozen=True)
class Event:
    """Evento de dominio listo para el wire SSE."""

    id: int | None
    name: str
    data: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(
            {"id": self.id, "event": self.name, "data": self.data},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "Event":
        payload = json.loads(raw)
        event_id = payload.get("id")
        return cls(
            id=int(event_id) if event_id is not None else None,
            name=str(payload.get("event") or "message"),
            data=payload.get("data") or {},
        )


class Subscription:
    """Cola de un cliente SSE, segura para publicar desde otros hilos."""

    def __init__(self, loop: asyncio.AbstractEventLoop, maxsize: int) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def push(self, event: Event) -> None:
        try:
            self._loop.call_soon_threadsafe(self._push_nowait, event)
        except RuntimeError:  # loop cerrado: el cliente ya se fue
            pass

    def _push_nowait(self, event: Event) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self.dropped += 1
            except asyncio.QueueEmpty:  # pragma: no cover - carrera benigna
                pass
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:  # pragma: no cover - carrera benigna
            pass

    async def get(self, timeout: float | None) -> Event | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
            return None

    def take_dropped(self) -> int:
        dropped, self.dropped = self.dropped, 0
        return dropped

    async def close(self) -> None:
        return None


class RedisSubscription(Subscription):
    """Adapta el pub/sub asíncrono de Redis al contrato de ``Subscription``."""

    def __init__(self, pubsub, client) -> None:  # type: ignore[no-untyped-def]
        self._pubsub = pubsub
        self._client = client
        self.dropped = 0

    async def get(self, timeout: float | None) -> Event | None:
        message = await self._pubsub.get_message(
            ignore_subscribe_messages=True,
            timeout=timeout if timeout is not None else 0.0,
        )
        if not message or message.get("type") != "message":
            return None
        return Event.from_json(message["data"])

    async def close(self) -> None:
        try:
            await self._pubsub.unsubscribe(CHANNEL)
        except Exception:  # pragma: no cover - cierre best-effort
            pass
        try:
            await self._pubsub.aclose()
        except Exception:  # pragma: no cover
            pass
        try:
            await self._client.aclose()
        except Exception:  # pragma: no cover
            pass


class Broker(Protocol):
    async def subscribe(self, loop: asyncio.AbstractEventLoop) -> Subscription: ...

    async def unsubscribe(self, subscription: Subscription) -> None: ...

    def publish(self, name: str, data: dict[str, Any]) -> Event: ...

    def replay_after(self, last_event_id: int | None) -> list[Event]: ...


class LocalBroker:
    """Fan-out en memoria para un solo proceso."""

    def __init__(
        self,
        *,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        replay_limit: int = DEFAULT_REPLAY_LIMIT,
    ) -> None:
        self._queue_size = queue_size
        self._replay_limit = replay_limit
        self._counter = itertools.count(1)
        self._recent: deque[Event] = deque(maxlen=replay_limit)
        self._subs: set[Subscription] = set()
        self._lock = threading.Lock()

    async def subscribe(self, loop: asyncio.AbstractEventLoop) -> Subscription:
        subscription = Subscription(loop, maxsize=self._queue_size)
        with self._lock:
            self._subs.add(subscription)
        return subscription

    async def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            self._subs.discard(subscription)

    def publish(self, name: str, data: dict[str, Any]) -> Event:
        with self._lock:
            event = Event(next(self._counter), name, data)
            self._recent.append(event)
            subscribers = list(self._subs)
        for subscription in subscribers:
            subscription.push(event)
        return event

    def replay_after(self, last_event_id: int | None) -> list[Event]:
        if last_event_id is None:
            return []
        with self._lock:
            recent = list(self._recent)
        return [
            event
            for event in recent
            if event.id is not None and event.id > last_event_id
        ]

    def reset(self) -> None:
        """Solo para tests: limpia suscriptores, buffer y contador."""

        with self._lock:
            self._subs.clear()
            self._recent.clear()
            self._counter = itertools.count(1)


class RedisBroker:
    """Pub/sub de Redis con buffer corto de replay para reconexiones."""

    def __init__(self, url: str, *, replay_limit: int = DEFAULT_REPLAY_LIMIT) -> None:
        import redis

        self._url = url
        self._replay_limit = replay_limit
        self._client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=2,
        )

    def ping(self) -> bool:
        return bool(self._client.ping())

    async def subscribe(self, loop: asyncio.AbstractEventLoop) -> Subscription:
        from redis.asyncio import Redis as AsyncRedis

        client = AsyncRedis.from_url(
            self._url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=None,
        )
        pubsub = client.pubsub()
        await pubsub.subscribe(CHANNEL)
        return RedisSubscription(pubsub, client)

    async def unsubscribe(self, subscription: Subscription) -> None:
        await subscription.close()

    def publish(self, name: str, data: dict[str, Any]) -> Event:
        event_id = int(self._client.incr(EVENT_SEQ_KEY))
        event = Event(event_id, name, data)
        raw = event.to_json()
        pipe = self._client.pipeline(transaction=False)
        pipe.lpush(RECENT_KEY, raw)
        pipe.ltrim(RECENT_KEY, 0, self._replay_limit - 1)
        pipe.expire(RECENT_KEY, RECENT_TTL_SECONDS)
        pipe.publish(CHANNEL, raw)
        pipe.execute()
        return event

    def replay_after(self, last_event_id: int | None) -> list[Event]:
        if last_event_id is None:
            return []
        raw_events = self._client.lrange(RECENT_KEY, 0, self._replay_limit - 1)
        events = [Event.from_json(raw) for raw in raw_events]
        events = [
            event
            for event in events
            if event.id is not None and event.id > last_event_id
        ]
        return sorted(events, key=lambda event: event.id or 0)


_broker: Broker | None = None
_broker_lock = threading.Lock()


def _build_broker() -> Broker:
    mode = os.getenv("REALTIME_BROKER", "").strip().lower()
    redis_url = os.getenv("REDIS_URL", "").strip()
    use_redis = mode == "redis" or (not mode and bool(redis_url))
    if use_redis:
        try:
            broker = RedisBroker(redis_url or "redis://localhost:6379/0")
            broker.ping()
            return broker
        except Exception:
            logger.warning(
                "Redis no disponible para tiempo real (%s); se usa el bus local "
                "y los eventos del worker no llegarán a este proceso.",
                redis_url or "redis://localhost:6379/0",
            )
    return LocalBroker()


def get_broker() -> Broker:
    global _broker
    with _broker_lock:
        if _broker is None:
            _broker = _build_broker()
        return _broker


def reset_broker() -> None:
    """Reinicia el singleton (tests y cambios de configuración)."""

    global _broker
    with _broker_lock:
        current = _broker
        _broker = None
    if isinstance(current, LocalBroker):
        current.reset()
