"""Ejecución de tools con un timeout explícito y numérico.

Las tools corren in-process, pero el timeout se aplica igualmente: si la capa
de servicio/repositorio se queda colgada (fichero bloqueado, base de datos
lenta), el grafo no espera indefinidamente. El valor por defecto es 3 segundos
y puede ajustarse por entorno.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import TypeVar

T = TypeVar("T")

DEFAULT_INCIDENT_TIMEOUT_SECONDS = 3.0
DEFAULT_INVENTORY_TIMEOUT_SECONDS = 3.0

INCIDENT_TIMEOUT_ENV = "AGENT_INCIDENT_TOOL_TIMEOUT_SECONDS"
INVENTORY_TIMEOUT_ENV = "AGENT_INVENTORY_TOOL_TIMEOUT_SECONDS"


class ToolTimeout(TimeoutError):
    """La tool no terminó dentro del timeout configurado."""


def _configured_timeout(env_name: str, default: float) -> float:
    raw = os.getenv(env_name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def incident_timeout_seconds() -> float:
    return _configured_timeout(
        INCIDENT_TIMEOUT_ENV, DEFAULT_INCIDENT_TIMEOUT_SECONDS
    )


def inventory_timeout_seconds() -> float:
    return _configured_timeout(
        INVENTORY_TIMEOUT_ENV, DEFAULT_INVENTORY_TIMEOUT_SECONDS
    )


def call_with_timeout(fn: Callable[[], T], timeout_seconds: float) -> T:
    """Ejecuta ``fn`` y falla con :class:`ToolTimeout` si excede el límite.

    ``shutdown(wait=False)`` evita que el hilo del grafo espere al trabajo que
    se quedó colgado; el resultado se descarta y la tool devuelve su fallback.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds debe ser mayor que cero.")

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError as exc:
        future.cancel()
        raise ToolTimeout(
            f"La tool no respondió en {timeout_seconds:g} segundos."
        ) from exc
    finally:
        executor.shutdown(wait=False)


__all__ = [
    "DEFAULT_INCIDENT_TIMEOUT_SECONDS",
    "DEFAULT_INVENTORY_TIMEOUT_SECONDS",
    "INCIDENT_TIMEOUT_ENV",
    "INVENTORY_TIMEOUT_ENV",
    "ToolTimeout",
    "call_with_timeout",
    "incident_timeout_seconds",
    "inventory_timeout_seconds",
]
