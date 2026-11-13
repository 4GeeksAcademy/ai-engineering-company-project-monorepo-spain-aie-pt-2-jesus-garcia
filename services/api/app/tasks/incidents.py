"""Tarea Celery que ejecuta el análisis pesado de un CSV de incidencias.

El mensaje solo transporta la ruta del fichero (nunca el contenido): el worker
lo lee del volumen compartido con la API.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from celery_app import celery_app

from ..incidents import service
from .dlq import record_dead_letter

logger = logging.getLogger("api.tasks.incidents")

RETRY_BACKOFF_SECONDS = float(
    os.getenv("CELERY_RETRY_BACKOFF_SECONDS", "5")
)


@celery_app.task(bind=True, name="incidents.analyze_csv", max_retries=3)
def analyze_incidents_csv(self, path: str, filename: str = "") -> dict:
    """Analiza un CSV y devuelve el resumen como dict serializable."""

    task_id = self.request.id or ""
    attempt = self.request.retries + 1
    started = time.perf_counter()

    logger.info(
        "task_id=%s attempt=%d status=started file=%s",
        task_id,
        attempt,
        filename,
    )

    try:
        result = service.analyze_path(path)
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        logger.exception(
            "task_id=%s attempt=%d status=failed duration_ms=%.1f error=%s",
            task_id,
            attempt,
            duration_ms,
            exc,
        )

        if self.request.retries < self.max_retries:
            countdown = RETRY_BACKOFF_SECONDS * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)

        record_dead_letter(
            task_id=task_id,
            task_name=self.name,
            attempts=attempt,
            max_retries=self.max_retries,
            error_message=f"{type(exc).__name__}: {exc}",
        )
        raise

    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "task_id=%s attempt=%d status=success duration_ms=%.1f",
        task_id,
        attempt,
        duration_ms,
    )

    Path(path).unlink(missing_ok=True)
    return result.model_dump()
