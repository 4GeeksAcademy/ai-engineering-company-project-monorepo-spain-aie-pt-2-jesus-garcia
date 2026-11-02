"""Instancia de Celery compartida por la API (productor) y el worker (consumidor).

Broker y result backend son el mismo Redis: la API encola y consulta estados,
mientras que un proceso worker independiente consume y ejecuta las tareas.
"""

from __future__ import annotations

import logging
import os

from celery import Celery
from celery.signals import celeryd_after_setup, worker_process_init, worker_ready

logger = logging.getLogger("api.celery")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "trackflow",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=("app.tasks.incidents",),
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # ACK solo al terminar: si el worker muere, el mensaje vuelve a la cola.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    # Toda tarea tiene timeout para no bloquear el pool indefinidamente.
    task_time_limit=int(os.getenv("CELERY_TASK_TIME_LIMIT", "600")),
    task_soft_time_limit=int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "540")),
    result_expires=int(os.getenv("CELERY_RESULT_EXPIRES", "86400")),
)


@celeryd_after_setup.connect
def _disable_fast_trace_before_consumer(sender=None, **kwargs) -> None:
    """Fuerza el tracer clásico antes de crear las clases Request.

    `create_request_cls` captura `app.use_fast_trace_task` al arrancar el
    consumidor. En macOS/Python 3.14 el atajo rápido revienta en el hijo
    prefork porque `trace._localized` queda vacío.
    """

    from celery.app import trace

    trace.reset_worker_optimizations(celery_app)


@worker_process_init.connect
def _disable_fast_trace(sender=None, **kwargs) -> None:
    """Refuerzo para hijos prefork con inicialización por spawn."""

    from celery.app import trace

    trace.reset_worker_optimizations(celery_app)


@worker_ready.connect
def _ensure_database_tables(sender=None, **kwargs) -> None:
    """Crea las tablas SQL necesarias en el worker (idempotente)."""

    from database import engine

    if engine is None:
        return

    import models  # noqa: F401  (registra DeadLetterTask en el metadata)
    from sqlmodel import SQLModel

    try:
        SQLModel.metadata.create_all(engine)
    except Exception:
        logger.exception("No se pudieron crear las tablas SQL del worker")
