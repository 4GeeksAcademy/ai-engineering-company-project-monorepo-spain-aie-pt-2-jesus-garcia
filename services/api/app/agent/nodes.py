"""Nodos del grafo del agente: una responsabilidad por nodo.

El clasificador decide si la pregunta necesita el RAG, una tool de lectura en
tiempo real o ambos. Los nodos ``retrieve`` y ``generate`` reutilizan el
pipeline RAG existente (``data/pipelines/rag.py``) sin duplicarlo. Las tools
leen de la misma capa de servicio que las rutas REST y devuelven fallbacks
honestos cuando no pueden confirmar un dato.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import ValidationError

from data.pipelines import rag

from .router import RoutingDecision, classify_question
from .state import AgentState
from .tool_answers import (
    format_incident_answer,
    format_inventory_answer,
    format_tool_context,
)
from .tools import (
    INCIDENT_TOOL_NAME,
    INVENTORY_TOOL_NAME,
    IncidentLookup,
    IncidentLookupInput,
    InventoryLookup,
    InventoryLookupInput,
    lookup_incident,
    lookup_inventory,
)

logger = logging.getLogger(__name__)

SAFE_ERROR_MESSAGE = (
    "No se pudo completar la consulta en este momento. "
    "Inténtalo de nuevo en unos minutos."
)

Retriever = Callable[[str], list[dict]]
Generator = Callable[[str, list[dict]], str]
Classifier = Callable[[str], RoutingDecision]


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if errors:
        message = str(errors[0].get("msg") or "Entrada inválida.")
        return message.removeprefix("Value error, ")
    return "Entrada inválida."


def _tool_output_dict(result) -> dict:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return dict(result)
    raise TypeError("La tool devolvió un resultado no serializable.")


def receive_question(state: AgentState) -> dict:
    """Normaliza la pregunta y decide si merece la pena clasificarla."""
    raw_question = state.get("question")
    question = raw_question.strip() if isinstance(raw_question, str) else ""
    if not question:
        logger.warning("Pregunta vacía: se evita la clasificación y el RAG.")
        return {
            "question": "",
            "status": "invalid_question",
            "error": "La pregunta no puede estar vacía.",
        }
    return {"question": question, "status": "ok", "error": None}


def make_classify_node(classifier: Classifier | None = None):
    """Construye el nodo que decide entre RAG, tool o ambos."""
    decide = classifier or classify_question

    def classify_node(state: AgentState) -> dict:
        question = state.get("question") or ""
        if state.get("status") == "invalid_question" or not question:
            return {"status": "invalid_question"}

        try:
            decision = decide(question)
            if isinstance(decision, dict):
                decision = RoutingDecision.model_validate(decision)
            if not isinstance(decision, RoutingDecision):
                raise TypeError(
                    "El clasificador debe devolver RoutingDecision."
                )
        except Exception:  # noqa: BLE001 - fallo controlado del clasificador
            logger.exception("Fallo al clasificar la pregunta")
            return {"status": "error", "error": SAFE_ERROR_MESSAGE}

        return {
            "route": decision.route,
            "routing": decision.model_dump(),
            "status": "ok",
            "error": None,
        }

    return classify_node


def make_retrieve_node(retriever: Retriever | None = None):
    """Construye el nodo que ejecuta ``retrieve`` sobre la base de conocimiento."""
    retrieve = retriever or rag.retrieve

    def retrieve_node(state: AgentState) -> dict:
        question = state.get("question") or ""
        if state.get("status") == "invalid_question" or not question:
            # Defensa: nunca se recupera sin una pregunta válida.
            return {"context": [], "status": "invalid_question"}

        try:
            context = retrieve(question)
        except Exception:  # noqa: BLE001 - se reporta como fallo controlado
            logger.exception("Fallo al recuperar contexto para la pregunta")
            return {"context": [], "status": "error", "error": SAFE_ERROR_MESSAGE}

        return {"context": list(context), "status": "ok", "error": None}

    return retrieve_node


def _construir_payload_incidente(routing: dict) -> IncidentLookupInput:
    filters = routing.get("filters") or {}
    return IncidentLookupInput(
        ticket_id=routing.get("ticket_id"),
        status=filters.get("status"),
        category=filters.get("category"),
        origin=filters.get("origin"),
        branch=filters.get("branch"),
    )


def _construir_payload_inventario(routing: dict) -> InventoryLookupInput:
    return InventoryLookupInput(
        sku_id=routing.get("sku_id"),
        sku_code=routing.get("sku_code"),
        name_query=routing.get("product_name"),
        warehouse=routing.get("warehouse"),
    )


def _tool_state(
    *,
    tool_name: str,
    data: dict,
) -> dict:
    error = data.get("error")
    status = error or ("ok" if data.get("found") else "not_found")
    return {
        "tool_name": tool_name,
        "tool_result": data,
        "tool_status": status,
        "tool_error": error,
        "fallback": not bool(data.get("ok")),
    }


def make_tool_incident_node(lookup: IncidentLookup | None = None):
    """Nodo de la tool de tickets (solo lectura)."""
    query = lookup or lookup_incident

    def tool_incident_node(state: AgentState) -> dict:
        if state.get("status") == "error":
            return {}

        role = str(state.get("user_role") or "")
        if role not in ("admin", "manager"):
            # Misma autorización que GET /api/incidents (require_manager).
            return _tool_state(
                tool_name=INCIDENT_TOOL_NAME,
                data={
                    "ok": False,
                    "found": False,
                    "incidents": [],
                    "error": "forbidden",
                    "message": (
                        "No tengo permisos para consultar tickets con tu rol."
                    ),
                },
            )

        routing = state.get("routing") or {}
        try:
            payload = _construir_payload_incidente(routing)
        except ValidationError as exc:
            return _tool_state(
                tool_name=INCIDENT_TOOL_NAME,
                data={
                    "ok": False,
                    "found": False,
                    "incidents": [],
                    "error": "invalid_input",
                    "message": _validation_message(exc),
                },
            )

        try:
            data = _tool_output_dict(query(payload))
        except Exception:  # noqa: BLE001 - la tool ya devuelve fallbacks
            logger.exception("Fallo no controlado en la tool de incidencias")
            data = {
                "ok": False,
                "found": False,
                "incidents": [],
                "error": "unavailable",
                "message": "No se pudo consultar el gestor de incidencias.",
            }

        return _tool_state(tool_name=INCIDENT_TOOL_NAME, data=data)

    return tool_incident_node


def make_tool_inventory_node(lookup: InventoryLookup | None = None):
    """Nodo de la tool de inventario (solo lectura)."""
    query = lookup or lookup_inventory

    def tool_inventory_node(state: AgentState) -> dict:
        if state.get("status") == "error":
            return {}

        routing = state.get("routing") or {}
        try:
            payload = _construir_payload_inventario(routing)
        except ValidationError as exc:
            return _tool_state(
                tool_name=INVENTORY_TOOL_NAME,
                data={
                    "ok": False,
                    "found": False,
                    "items": [],
                    "error": "invalid_input",
                    "message": _validation_message(exc),
                },
            )

        try:
            data = _tool_output_dict(query(payload))
        except Exception:  # noqa: BLE001 - la tool ya devuelve fallbacks
            logger.exception("Fallo no controlado en la tool de inventario")
            data = {
                "ok": False,
                "found": False,
                "items": [],
                "error": "unavailable",
                "message": "No se pudo consultar el inventario.",
            }

        return _tool_state(tool_name=INVENTORY_TOOL_NAME, data=data)

    return tool_inventory_node


def answer_from_tool_node(state: AgentState) -> dict:
    """Responde con los datos de la tool, sin pasar por el LLM.

    Es la ruta principal cuando la pregunta es solo de ticket o de stock y el
    fallback honesto cuando la tool no pudo confirmar el dato. En rutas
    ``+rag`` sin contexto recuperado, añade una nota para no ocultar que la
    base de conocimiento no aportó información adicional.
    """
    tool_name = state.get("tool_name")
    result = state.get("tool_result") or {}

    if tool_name == INVENTORY_TOOL_NAME:
        answer = format_inventory_answer(result)
    elif tool_name == INCIDENT_TOOL_NAME:
        answer = format_incident_answer(result)
    else:
        answer = (
            "No pude confirmar ese dato ahora mismo. Inténtalo de nuevo en "
            "unos minutos."
        )

    route = state.get("route") or ""
    if route.endswith("+rag") and not state.get("context"):
        answer = (
            f"{answer}\n\nNo encontré información adicional en la base de "
            "conocimiento para completar la consulta."
        )

    return {
        "answer": answer,
        "status": "ok",
        "fallback": bool(state.get("fallback")),
        "error": None,
    }


def make_generate_node(generator: Generator | None = None):
    """Construye el nodo que genera la respuesta con contexto RAG y de tools."""
    generate = generator or rag.generate_answer

    def generate_node(state: AgentState) -> dict:
        question = state.get("question") or ""
        context = list(state.get("context") or [])
        if not context:
            # El enrutado ya evita este caso; se mantiene como red de seguridad
            # para que jamás se llame al LLM sin contexto.
            return {"answer": rag.NO_CONTEXT_ANSWER, "status": "no_context"}

        tool_context = format_tool_context(
            state.get("tool_name"),
            state.get("tool_result") or {},
        )
        if tool_context is not None:
            context.append(tool_context)

        try:
            answer = generate(question, context)
        except Exception:  # noqa: BLE001 - se reporta como fallo controlado
            logger.exception("Fallo al generar la respuesta RAG")
            return {"status": "error", "error": SAFE_ERROR_MESSAGE}

        if not isinstance(answer, str) or not answer.strip():
            logger.error("El generador devolvió una respuesta vacía o no textual.")
            return {"status": "error", "error": SAFE_ERROR_MESSAGE}

        return {
            "answer": answer.strip(),
            "status": "ok",
            "error": None,
            "tool_context_included": tool_context is not None,
        }

    return generate_node


def no_context_node(state: AgentState) -> dict:
    """Responde con honestidad cuando la recuperación no supera el umbral."""
    return {"answer": rag.NO_CONTEXT_ANSWER, "status": "no_context", "error": None}


def fail_node(state: AgentState) -> dict:
    """Salida terminal segura para preguntas inválidas o fallos internos."""
    status = state.get("status")
    if status not in ("invalid_question", "error"):
        status = "error"
    return {
        "status": status,
        "error": state.get("error") or SAFE_ERROR_MESSAGE,
        "answer": "",
    }


__all__ = [
    "Classifier",
    "Generator",
    "Retriever",
    "SAFE_ERROR_MESSAGE",
    "answer_from_tool_node",
    "fail_node",
    "make_classify_node",
    "make_generate_node",
    "make_retrieve_node",
    "make_tool_incident_node",
    "make_tool_inventory_node",
    "no_context_node",
    "receive_question",
]
