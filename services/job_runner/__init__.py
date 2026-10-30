"""Ciclo de vida de los procesos en segundo plano (`job_runs`).

El estado es el dato: cada ejecución programada existe como fila antes de
empezar el trabajo y termina siempre en un estado terminal.
"""

from .models import (
    JOB_NAME_NIGHTLY_EXPORT,
    JOB_STATUSES,
    TERMINAL_STATUSES,
    JobRun,
    create_job_runs_table,
)

__all__ = [
    "JOB_NAME_NIGHTLY_EXPORT",
    "JOB_STATUSES",
    "TERMINAL_STATUSES",
    "JobRun",
    "create_job_runs_table",
]
