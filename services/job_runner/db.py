"""Conexión a la BD operativa donde vive ``job_runs``."""

from __future__ import annotations

import os

from sqlalchemy.engine import Engine
from sqlmodel import create_engine


def get_database_url() -> str:
    """URL de la BD del job runner.

    ``JOB_DATABASE_URL`` permite aislar el job de la API; ``DATABASE_URL`` es el
    fallback y es la que comparten ambos en Docker/Supabase.
    """

    url = os.getenv("JOB_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL (o JOB_DATABASE_URL) para escribir en job_runs."
        )
    if url.startswith("postgresql://"):
        # Igual que services/api/database.py: el driver es psycopg2, no psycopg3.
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_database_url(), pool_pre_ping=True)
