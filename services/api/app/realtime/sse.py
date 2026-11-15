"""Formato de wire de Server-Sent Events (SSE).

El framing es explícito: ``event:`` con nombre, ``data:`` con JSON compacto en
una sola línea y ``id:`` cuando el evento admite replay. El keep-alive viaja
como comentario (``: keep-alive``) porque SSE ignora las líneas que empiezan
por dos puntos.
"""

from __future__ import annotations

import json
import os

from .broker import Event

SSE_MEDIA_TYPE = "text/event-stream"

# ``X-Accel-Buffering: no`` evita que nginx acumule el stream; ``no-transform``
# impide que proxies compriman/reescriban los frames.
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

RETRY_FRAME = "retry: 3000\n\n"
KEEPALIVE_FRAME = ": keep-alive\n\n"

DEFAULT_KEEPALIVE_SECONDS = 15.0


def format_frame(event: Event) -> str:
    """Serializa un evento como frame SSE completo."""

    lines: list[str] = []
    if event.id is not None:
        lines.append(f"id: {event.id}")
    lines.append(f"event: {event.name}")
    # ``json.dumps`` compacto garantiza una única línea ``data:``, que es lo
    # que exige el ejemplo del briefing (sin sobre {"event","data"}).
    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


def keepalive_seconds() -> float:
    raw = os.getenv("SSE_KEEPALIVE_SECONDS", str(DEFAULT_KEEPALIVE_SECONDS))
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_KEEPALIVE_SECONDS
    return max(0.01, value)
