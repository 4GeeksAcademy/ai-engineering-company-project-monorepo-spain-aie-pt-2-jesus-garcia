"""Dead Letter Queue: tareas que agotaron todos sus reintentos.

El registro durable vive en la tabla SQL ``dead_letter_tasks``; además se
publica una entrada en la lista Redis ``dlq:trackflow`` para inspección rápida
(``redis-cli LRANGE dlq:trackflow 0 -1``).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import redis
from sqlmodel import Session, select

from database import engine
from models import DeadLetterTask

logger = logging.getLogger("api.tasks.dlq")

DLQ_KEY = os.getenv("CELERY_DLQ_KEY", "dlq:trackflow")


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )


def record_dead_letter(
    *,
    task_id: str,
    task_name: str,
    attempts: int,
    max_retries: int,
    error_message: str,
) -> None:
    """Persiste el fallo definitivo en SQL y lo publica en la lista Redis."""

    payload = {
        "task_id": task_id,
        "task_name": task_name,
        "attempts": attempts,
        "max_retries": max_retries,
        "error": error_message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if engine is None:
        logger.error(
            "task_id=%s status=dlq_db_skipped reason=DATABASE_URL_unset",
            task_id,
        )
    else:
        try:
            with Session(engine) as session:
                existing = session.exec(
                    select(DeadLetterTask).where(
                        DeadLetterTask.task_id == task_id
                    )
                ).first()
                if existing is None:
                    session.add(
                        DeadLetterTask(
                            task_id=task_id,
                            task_name=task_name,
                            attempts=attempts,
                            max_retries=max_retries,
                            error_message=error_message,
                        )
                    )
                    session.commit()
        except Exception:
            logger.exception("task_id=%s status=dlq_db_error", task_id)

    try:
        _redis_client().rpush(DLQ_KEY, json.dumps(payload))
    except Exception:
        logger.exception("task_id=%s status=dlq_redis_error", task_id)

    logger.error(
        "task_id=%s status=dlq attempts=%d max_retries=%d error=%s",
        task_id,
        attempts,
        max_retries,
        error_message,
    )
