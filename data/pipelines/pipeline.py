"""Entrypoint de entrega del pipeline de desempeño de negocio.

La implementación vive en ``pipelines/weekly_performance/``. Este archivo es la
puerta de entrada exigida por la entrega y permite ejecutar el pipeline por
script:

    python data/pipelines/pipeline.py run --lookback 3
    python data/pipelines/pipeline.py backfill --week 2026-07-13
    python data/pipelines/pipeline.py reconcile-source --days 7

También expone los flows de Prefect para inspección o despliegue:
``weekly_flow``, ``process_week`` y ``source_reconciliation_flow``.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Permite ejecutar el archivo directamente desde cualquier directorio.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.weekly_performance.cli import main  # noqa: E402
from pipelines.weekly_performance.flow import (  # noqa: E402
    process_week,
    source_reconciliation_flow,
    weekly_flow,
)

__all__ = [
    "main",
    "process_week",
    "source_reconciliation_flow",
    "weekly_flow",
]

if __name__ == "__main__":
    raise SystemExit(main())
