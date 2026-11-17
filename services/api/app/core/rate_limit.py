"""Rate limiting en memoria (sliding window) para endpoints sensibles.

Un único proceso de la API mantiene su propio contador. En un despliegue con
varios workers el límite es por worker; para un límite global se sustituiría
por Redis. Aun así, esta capa corta fuerza bruta y abuso trivial sin añadir
infraestructura.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

_TRUTHY = {"1", "true", "yes", "on"}


def rate_limit_enabled() -> bool:
    raw = (os.getenv("RATE_LIMIT_ENABLED") or "1").strip().lower()
    return raw in _TRUTHY


class SlidingWindowLimiter:
    """Contador thread-safe por clave con ventana deslizante."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float) -> int:
        """Registra un intento. Devuelve 0 si se permite o los segundos de espera."""

        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(
                    1, int(window_seconds - (now - bucket[0])) + 1
                )
                return retry_after
            bucket.append(now)
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_identity(request: Request) -> str:
    """IP real detrás de proxy, o la del socket."""

    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    limit: int,
    window_seconds: float,
    identifier: str | None = None,
) -> None:
    """Aplica el límite o lanza 429 con ``Retry-After``."""

    if not rate_limit_enabled():
        return
    key = f"{bucket}:{client_identity(request)}"
    if identifier:
        key = f"{key}:{identifier.strip().lower()}"
    retry_after = limiter.hit(key, limit, window_seconds)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas solicitudes. Inténtalo de nuevo más tarde.",
            headers={"Retry-After": str(retry_after)},
        )


def reset_rate_limits() -> None:
    limiter.reset()


__all__ = [
    "SlidingWindowLimiter",
    "client_identity",
    "enforce_rate_limit",
    "limiter",
    "rate_limit_enabled",
    "reset_rate_limits",
]
