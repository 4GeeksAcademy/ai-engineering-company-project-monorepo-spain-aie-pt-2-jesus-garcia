"""Log operativo de los jobs.

Formato de una línea por evento, pensado para ``docker compose logs``::

    2026-10-30T02:15:03Z level=INFO job=nightly_export status=processing target_date=2026-10-29 run_id=42 msg="trabajo iniciado"

Toda línea lleva timestamp UTC, nombre del job y estado resultante.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import sys

JOB_LOGGER_NAME = "trackflow.jobs"

LOG_FORMAT = "%(asctime)s level=%(levelname)s %(message)s"


class UTCFormatter(logging.Formatter):
    """Timestamp ISO-8601 en UTC, independiente del TZ del contenedor."""

    def formatTime(self, record, datefmt=None):  # noqa: N802 (API de logging)
        return datetime.fromtimestamp(record.created, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )


def configure_logging(level: str | int = "INFO") -> None:
    """Configura el handler de stdout (idempotente)."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(UTCFormatter(LOG_FORMAT))
    handler._trackflow_job_handler = True  # type: ignore[attr-defined]

    root = logging.getLogger()
    root.handlers = [
        existing
        for existing in root.handlers
        if not getattr(existing, "_trackflow_job_handler", False)
    ]
    root.addHandler(handler)
    root.setLevel(level)


class JobLogger:
    """Emite eventos con ``job`` y ``status`` en todas las líneas."""

    def __init__(self, job_name: str) -> None:
        self.job_name = job_name
        self._logger = logging.getLogger(f"{JOB_LOGGER_NAME}.{job_name}")

    def _emit(self, level: int, status: str, message: str, **fields) -> None:
        parts = [f"job={self.job_name}", f"status={status}"]
        for key, value in fields.items():
            if value is None:
                continue
            parts.append(f"{key}={value}")
        safe_message = " ".join(str(message).split()).replace('"', "'")
        parts.append(f'msg="{safe_message}"')
        self._logger.log(level, " ".join(parts))

    def info(self, status: str, message: str, **fields) -> None:
        self._emit(logging.INFO, status, message, **fields)

    def warning(self, status: str, message: str, **fields) -> None:
        self._emit(logging.WARNING, status, message, **fields)

    def error(self, status: str, message: str, **fields) -> None:
        self._emit(logging.ERROR, status, message, **fields)
