"""Estado mínimo compartido por los nodos del grafo del agente."""

from __future__ import annotations

from typing import Literal, TypedDict

AgentStatus = Literal["ok", "invalid_question", "no_context", "error"]
AgentRoute = Literal["rag", "incident", "inventory", "incident+rag", "inventory+rag"]
ToolStatus = Literal[
    "ok",
    "not_found",
    "invalid_input",
    "forbidden",
    "timeout",
    "unavailable",
]


class AgentState(TypedDict, total=False):
    """Información mínima que un nodo necesita para decidir el siguiente paso.

    No se guarda el historial de la conversación: cada corrida es stateless y
    el agente solo necesita la pregunta actual, la ruta decidida y el resultado
    de la tool (si se usó). Los detalles de ejecución (orden de nodos,
    duraciones, checkpoints) viven en el trace, no en el estado.
    """

    question: str
    """Pregunta normalizada (sin espacios sobrantes)."""

    context: list[dict]
    """Payloads devueltos por ``retrieve``; se pasan a la generación."""

    answer: str
    """Respuesta final o mensaje seguro de error."""

    status: AgentStatus
    """Resultado de la corrida; el endpoint lo mapea a HTTP."""

    error: str | None
    """Mensaje apto para el cliente. Nunca incluye stack traces."""

    run_id: str
    """Identificador de corrida, también usado como ``thread_id``."""

    user_role: str
    """Rol del usuario autenticado (admin/manager/user) para autorizar tools."""

    route: AgentRoute
    """Fuente(s) decididas por el clasificador."""

    routing: dict
    """Decisión completa del clasificador (argumentos y motivo)."""

    tool_name: str
    """``incident_lookup`` o ``inventory_lookup`` cuando se usó una tool."""

    tool_result: dict
    """Salida tipada de la tool serializada como dict."""

    tool_status: ToolStatus
    """Resultado de la tool: ok, not_found, timeout, unavailable, etc."""

    tool_error: str | None
    """Código de error de la tool, si lo hubo."""

    fallback: bool
    """True cuando la respuesta se apoya en un fallback honesto."""

    tool_context_included: bool
    """True cuando el generador recibió además el resultado de una tool."""
