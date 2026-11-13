"""Agente RAG de TrackFlow (grafo LangGraph sobre el pipeline de ``data/``).

El paquete se importa de dos formas distintas:

* ``app.agent.*`` cuando la API corre desde ``services/api`` (uvicorn/pytest).
* ``services.api.app.agent.*`` cuando lo importan los evals desde la raíz del
  monorepo.

En ambos casos el grafo necesita ``data.pipelines.rag``; se garantiza que la
raíz del monorepo esté en ``sys.path`` antes de importar cualquier submódulo.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    _REPO_ROOT = Path(__file__).resolve().parents[4]
except IndexError:  # Docker: /app/app/agent/__init__.py
    _REPO_ROOT = Path("/app")

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
