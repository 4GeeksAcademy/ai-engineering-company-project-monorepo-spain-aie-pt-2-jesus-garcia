"""Router SSE de notificaciones en tiempo real.

Una conexión por cliente, todas independientes entre sí: cada una recibe su
propia copia del evento. La infraestructura —el bus de eventos— es compartida
(fan-out en memoria o pub/sub de Redis en Docker).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import require_manager
from app.realtime.broker import Broker, Event, get_broker
from app.realtime.events import STREAM_LAGGED
from app.realtime.sse import (
    KEEPALIVE_FRAME,
    RETRY_FRAME,
    SSE_HEADERS,
    SSE_MEDIA_TYPE,
    format_frame,
    keepalive_seconds,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["realtime"])


def _parse_cursor(raw: str | None) -> int | None:
    """Último evento confirmado por el cliente (cabecera o query)."""

    if raw is None:
        return None
    try:
        cursor = int(raw.strip())
    except (TypeError, ValueError):
        return None
    return cursor if cursor >= 0 else None


async def _event_source(
    broker: Broker,
    cursor: int | None,
    keepalive: float,
):
    """Generador SSE: preámbulo, replay corto y eventos en vivo."""

    loop = asyncio.get_running_loop()
    subscription = await broker.subscribe(loop)
    try:
        # ``retry`` es la pista estándar de SSE para clientes que la respeten;
        # el backoff real (progresivo + jitter) lo aplica el fetch del cliente.
        yield RETRY_FRAME

        history = await run_in_threadpool(broker.replay_after, cursor)
        for event in history:
            yield format_frame(event)

        while True:
            event = await subscription.get(keepalive)
            dropped = subscription.take_dropped()
            if dropped:
                # El cliente se atrasó: se descartó cola y debe reconciliar
                # con el snapshot REST. No se inventan eventos perdidos.
                yield format_frame(
                    Event(None, STREAM_LAGGED, {"dropped": dropped})
                )
            if event is None:
                yield KEEPALIVE_FRAME
                continue
            yield format_frame(event)
    finally:
        await broker.unsubscribe(subscription)
        await subscription.close()


@router.get(
    "/stream",
    summary="Stream SSE de notificaciones (JWT del backoffice)",
    response_class=StreamingResponse,
)
async def stream_events(
    request: Request,
    last_event_id: str | None = Query(default=None),
    _=Depends(require_manager),
) -> StreamingResponse:
    broker = get_broker()
    header_cursor = request.headers.get("last-event-id")
    cursor = _parse_cursor(
        header_cursor if header_cursor is not None else last_event_id
    )
    return StreamingResponse(
        _event_source(broker, cursor, keepalive_seconds()),
        media_type=SSE_MEDIA_TYPE,
        headers=dict(SSE_HEADERS),
    )
