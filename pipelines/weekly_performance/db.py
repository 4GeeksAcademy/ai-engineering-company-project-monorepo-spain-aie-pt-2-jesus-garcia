"""Creación y caché de engines SQLAlchemy del pipeline."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from .settings import get_database_url


@lru_cache(maxsize=8)
def get_engine(url: str | None = None) -> Engine:
    """Devuelve un engine para ``url`` (o para la URL del entorno).

    En PostgreSQL se fija la sesión en UTC para que los ``timestamp with time
    zone`` y los ``date`` se comparen de forma determinista.
    """

    resolved = url or get_database_url()
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if resolved.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    elif resolved.startswith("postgresql"):
        kwargs["connect_args"] = {"options": "-c timezone=UTC"}
    return create_engine(resolved, **kwargs)


def clear_engine_cache() -> None:
    """Limpia la caché (útil en tests que cambian ``DATABASE_URL_PIPELINE``)."""

    get_engine.cache_clear()
