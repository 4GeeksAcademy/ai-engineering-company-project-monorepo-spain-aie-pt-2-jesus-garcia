"""Lock de concurrencia por semana.

En PostgreSQL se usa un advisory lock de sesión: se mantiene mientras dura la
corrida y se libera al cerrar la conexión, incluso si el worker muere. En SQLite
(local/tests) es un no-op porque el pipeline se ejecuta en un solo proceso.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from typing import Iterator

from sqlalchemy import Engine, text

from .settings import PIPELINE_NAME


def advisory_key(week_start) -> int:
    """Clave bigint estable y determinista para ``(pipeline, semana)``."""

    digest = hashlib.sha256(
        f"{PIPELINE_NAME}:{week_start.isoformat()}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@contextmanager
def week_lock(engine: Engine, week_start) -> Iterator[bool]:
    """Intenta adquirir el lock de la semana.

    Devuelve ``True`` si se puede procesar y ``False`` si otra corrida de la
    misma semana lo tiene. En SQLite siempre devuelve ``True``.
    """

    if engine.dialect.name != "postgresql":
        yield True
        return

    key = advisory_key(week_start)
    with engine.connect() as conn:
        acquired = bool(
            conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
            ).scalar()
        )
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            try:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": key}
                )
                conn.commit()
            except Exception:
                # Al cerrar la conexión PostgreSQL libera el lock de sesión.
                conn.rollback()
