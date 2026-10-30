"""Contexto común para los tests del entrypoint de entrega del pipeline."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys

# pytest inserta el directorio del test (``tests/pipelines``) en ``sys.path``,
# no la raíz del monorepo. Se añade para poder importar ``pipelines`` y cargar
# ``data/pipelines/pipeline.py``.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Igual que la suite del pipeline: evita que Prefect intente hablar con su API
# durante los tests y que el servidor efímero escriba en streams cerrados.
os.environ["PREFECT_LOGGING_TO_API_ENABLED"] = "false"
os.environ["PREFECT_LOGGING_TO_API_WHEN_MISSING_FLOW"] = "ignore"
os.environ.setdefault("PREFECT_LOGGING_SERVER_LEVEL", "CRITICAL")
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")
logging.getLogger("prefect").setLevel(logging.CRITICAL)
