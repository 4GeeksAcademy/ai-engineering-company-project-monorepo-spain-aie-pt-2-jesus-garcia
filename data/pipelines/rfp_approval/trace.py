"""Trazabilidad por ejecución de nodo (agente, input, output, timestamp)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

MAX_TRACE_CHARS = 3_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact(value: Any, *, depth: int = 0) -> Any:
    """Recorta payloads grandes para que la traza sea legible y barata."""

    if depth > 4:
        return "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= MAX_TRACE_CHARS:
            return value
        return value[:MAX_TRACE_CHARS] + "…"
    if isinstance(value, (list, tuple)):
        items = [_compact(item, depth=depth + 1) for item in list(value)[:20]]
        if len(value) > 20:
            items.append(f"… ({len(value) - 20} más)")
        return items
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 40:
                result["…"] = f"{len(value) - 40} claves más"
                break
            result[str(key)] = _compact(item, depth=depth + 1)
        return result
    return str(value)


def compact(value: Any) -> Any:
    return _compact(value)


def trace_event(
    *,
    part: int,
    node: str,
    agent: str,
    input: dict | None = None,
    output: dict | None = None,
    department_id: str | None = None,
    timestamp: str | None = None,
    duration_ms: int | None = None,
) -> dict:
    """Registro inmutable de una ejecución de nodo."""

    return {
        "event_id": str(uuid4()),
        "part": part,
        "node": node,
        "agent": agent,
        "department_id": department_id,
        "input": compact(input or {}),
        "output": compact(output or {}),
        "timestamp": timestamp or utc_now(),
        "duration_ms": duration_ms,
    }


def trace_json(events: list[dict]) -> str:
    return json.dumps(compact(events), ensure_ascii=False, indent=2, default=str)


__all__ = [
    "MAX_TRACE_CHARS",
    "compact",
    "trace_event",
    "trace_json",
    "utc_now",
]
