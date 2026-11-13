"""Tests del engine del pipeline (normalización del driver)."""

from __future__ import annotations

from pipelines.weekly_performance.db import clear_engine_cache, get_engine


def test_postgresql_url_is_pinned_to_psycopg2():
    """`postgresql://` no debe depender de la versión de SQLAlchemy.

    SQLAlchemy 2.1 resuelve `postgresql://` a psycopg3, que no está instalado
    en las imágenes del pipeline ni del worker; el engine fija psycopg2.
    """

    engine = get_engine("postgresql://user:pass@localhost:5432/trackflow")
    try:
        assert engine.url.drivername == "postgresql+psycopg2"
    finally:
        engine.dispose()
        clear_engine_cache()


def test_explicit_driver_is_preserved():
    engine = get_engine("postgresql+psycopg2://user:pass@localhost:5432/db")
    try:
        assert engine.url.drivername == "postgresql+psycopg2"
    finally:
        engine.dispose()
        clear_engine_cache()
