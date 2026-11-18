"""Estado mínimo compartido por los nodos del grafo del agente."""

from __future__ import annotations

from typing import Literal, TypedDict

AgentStatus = Literal["ok", "invalid_question", "no_context", "error"]


class AgentState(TypedDict, total=False):
    """Información mínima que un nodo necesita para decidir el siguiente paso.

    No se guarda el historial de la conversación: cada corrida es stateless y
    el RAG solo necesita la pregunta actual y el contexto recuperado. Los
    detalles de ejecución (orden de nodos, duraciones, checkpoints) viven en el
    trace, no en el estado.
    """

    question: str
    """Pregunta normalizada (sin espacios sobrantes)."""

    context: list[dict]
    """Payloads devueltos por ``retrieve``; se pasan tal cual a la generación."""

    answer: str
    """Respuesta final o mensaje seguro de error."""

    status: AgentStatus
    """Resultado de la corrida; el endpoint lo mapea a HTTP."""

    error: str | None
    """Mensaje apto para el cliente. Nunca incluye stack traces."""

    run_id: str
    """Identificador de corrida, también usado como ``thread_id`` del checkpointer."""
