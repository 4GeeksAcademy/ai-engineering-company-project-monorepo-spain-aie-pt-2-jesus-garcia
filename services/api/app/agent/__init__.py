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

# Las tools del agente importan ``database``, ``models`` y ``schemas``, que
# viven en la raíz de ``services/api``. Cuando el paquete se importa como
# ``services.api.app.agent`` desde la raíz del monorepo (evals), esa ruta no
# está en ``sys.path``; se añade aquí para que ambos modos de importación
# funcionen sin duplicar módulos de configuración.
try:
    _API_ROOT = Path(__file__).resolve().parents[2]
except IndexError:  # Docker: /app/app/agent/__init__.py
    _API_ROOT = Path("/app")

if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))
