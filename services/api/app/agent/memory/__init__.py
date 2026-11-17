"""Memoria persistente y explícita del agente de TrackFlow.

El paquete no escribe en las colecciones RAG de la empresa. La memoria vive en
tablas propias (``agent_memory_*``) sobre el engine SQLModel de la API. Este
``__init__`` se mantiene deliberadamente ligero: el store (que importa la base
de datos) no se carga al importar el paquete, para que el grafo y sus evals
puedan usar la generación con memoria sin abrir una conexión.
"""

from __future__ import annotations

from .schemas import (
    MemoryProposalDraft,
    MemoryProposalView,
    MemoryResolutionView,
    MemoryScope,
)

__all__ = [
    "MemoryProposalDraft",
    "MemoryProposalView",
    "MemoryResolutionView",
    "MemoryScope",
]
