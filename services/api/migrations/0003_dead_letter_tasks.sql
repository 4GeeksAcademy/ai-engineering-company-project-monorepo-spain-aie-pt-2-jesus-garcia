-- 0003 — Dead Letter Queue de tareas Celery.
-- Aditiva e idempotente: se puede aplicar varias veces sin error.

CREATE TABLE IF NOT EXISTS dead_letter_tasks (
    id BIGSERIAL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    task_name VARCHAR(255) NOT NULL,
    attempts INTEGER NOT NULL,
    max_retries INTEGER NOT NULL,
    error_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_dead_letter_tasks_task_id
    ON dead_letter_tasks (task_id);
