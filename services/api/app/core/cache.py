"""Caché en memoria con TTL para respuestas del API.

Caché local por proceso (dict + RLock). Válida para un único worker de uvicorn;
con múltiples workers haría falta una caché compartida (Redis).
"""

import threading
import time

Entry = tuple[float, object]


class TTLCache:
    def __init__(self, default_ttl: float | None = None) -> None:
        self._default_ttl = default_ttl
        self._store: dict[str, Entry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _expiry(self, ttl: float | None) -> float:
        if ttl is not None:
            return time.monotonic() + ttl
        if self._default_ttl is not None:
            return time.monotonic() + self._default_ttl
        return float("inf")

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            expires_at, value = entry
            if expires_at <= time.monotonic():
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value, ttl: float | None = None) -> None:
        with self._lock:
            self._store[key] = (self._expiry(ttl), value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [key for key in self._store if key.startswith(prefix)]
            for key in keys:
                del self._store[key]
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, float]:
        with self._lock:
            now = time.monotonic()
            size = sum(1 for expires_at, _ in self._store.values() if expires_at > now)
            total = self._hits + self._misses
            return {
                "size": size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": (self._hits / total) if total else 0.0,
            }


cache = TTLCache()


def cached(cache: TTLCache, key: str, ttl: float, compute):
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = compute()
    cache.set(key, value, ttl=ttl)
    return value