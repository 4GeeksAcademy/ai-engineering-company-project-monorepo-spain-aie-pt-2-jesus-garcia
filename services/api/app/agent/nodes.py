"""Nodos del grafo del agente: una responsabilidad por nodo.

El clasificador decide si la pregunta necesita el RAG, una tool de lectura en
tiempo real o ambos. Los nodos ``retrieve`` y ``generate`` reutilizan el
pipeline RAG existente (``data/pipelines/rag.py``) sin duplicarlo. Las tools
leen de la misma capa de servicio que las rutas REST y devuelven fallbacks
honestos cuando no pueden confirmar un dato.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable

from langgraph.config import get_stream_writer
from pydantic import ValidationError

from data.pipelines import rag

from .harness.external import isolate_context
from .harness.observability import CATEGORY_SECURITY, GuardrailEvent, metrics
from .memory.evaluation import evaluate_interaction
from .memory.gate import is_memory_candidate
from .memory.generation import (
    answer_from_memory,
    answer_uses_memory,
    generate_with_memory,
    memory_notes,
)
from .memory.schemas import EvaluationOutcome, GenerationOutcome
from .rag_policy import filter_context_for_role
from .router import RoutingDecision, classify_question
from .state import AgentState
from .streaming import GenerationAborted, current_abort, streaming_enabled
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
MemoryGenerator = Callable[[str, list[dict], list[dict]], GenerationOutcome]
MemoryEvaluator = Callable[..., EvaluationOutcome]
MemoryGate = Callable[[str], bool]


def _supports_policy_correction(generator: Callable[..., object]) -> bool:
    """True si el generador inyectado acepta la corrección de país."""

    try:
        return "policy_correction" in inspect.signature(generator).parameters
    except (TypeError, ValueError):
        return False


def _supported_kwargs(
    generator: Callable[..., object],
    **kwargs: object,
) -> dict[str, object]:
    """Filtra kwargs para generadores inyectados con firmas antiguas."""

    try:
        signature = inspect.signature(generator)
    except (TypeError, ValueError):
        return {}
    accepts_extra = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if accepts_extra:
        return dict(kwargs)
    return {
        key: value
        for key, value in kwargs.items()
        if key in signature.parameters
    }


def _proposal_dict(outcome) -> dict | None:
    proposal = getattr(outcome, "proposal", None)
    if proposal is None:
        return None
    if hasattr(proposal, "model_dump"):
        return proposal.model_dump()
    if isinstance(proposal, dict):
        return dict(proposal)
    return None


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

        isolated = isolate_context(
            list(context),
            run_id=state.get("run_id"),
            session_id=state.get("session_id"),
        )
        isolated = filter_context_for_role(isolated, state.get("user_role"))
        return {"context": isolated, "status": "ok", "error": None}

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

        role = str(state.get("user_role") or "")
        if role not in ("admin", "manager"):
            # El inventario es dato operativo B2B: un usuario final no puede
            # consultar stock ni el client_id de otras marcas.
            return _tool_state(
                tool_name=INVENTORY_TOOL_NAME,
                data={
                    "ok": False,
                    "found": False,
                    "items": [],
                    "error": "forbidden",
                    "message": (
                        "No tengo permisos para consultar inventario con tu rol."
                    ),
                },
            )

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


def make_answer_from_tool_node(gate: MemoryGate | None = None):
    """Responde con los datos de la tool, sin pasar por el LLM.

    Es la ruta principal cuando la pregunta es solo de ticket o de stock y el
    fallback honesto cuando la tool no pudo confirmar el dato. En rutas
    ``+rag`` sin contexto recuperado, añade una nota para no ocultar que la
    base de conocimiento no aportó información adicional. Si hay memoria
    relevante, la añade de forma determinista.
    """
    memory_gate = gate or is_memory_candidate

    def answer_from_tool_node(state: AgentState) -> dict:
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

        notes = memory_notes(state.get("memory_context"))
        if notes:
            answer = f"{answer}\n\n{notes}"

        return {
            "answer": answer,
            "status": "ok",
            "fallback": bool(state.get("fallback")),
            "error": None,
            "memory_used": bool(notes),
            "memory_gate_applicable": bool(
                memory_gate(state.get("question") or "")
            ),
        }

    return answer_from_tool_node


answer_from_tool_node = make_answer_from_tool_node()


def make_generate_node(
    generator: Generator | None = None,
    memory_generator: MemoryGenerator | None = None,
):
    """Construye el nodo que genera la respuesta con contexto RAG y de tools.

    Si se inyecta ``generator`` (evals antiguas) se mantiene el contrato de dos
    argumentos y no se propone memoria. En producción se usa el generador con
    memoria: una sola llamada devuelve respuesta + propuesta estructurada.
    """

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
            if tool_context.get("neutralized"):
                metrics.record(
                    GuardrailEvent(
                        guard="external_content_guard",
                        category=CATEGORY_SECURITY,
                        action="sanitized",
                        reason="instruction_in_tool_result",
                        run_id=state.get("run_id"),
                        session_id=state.get("session_id"),
                        snippet="resultado de tool con instrucciones neutralizadas",
                    )
                )
            context.append(tool_context)

        memory_context = list(state.get("memory_context") or [])
        policy_correction = state.get("policy_correction")
        conversation_history = list(state.get("conversation_context") or [])
        on_token = None
        if streaming_enabled():
            writer = get_stream_writer()

            def on_token(text: str) -> None:
                writer({"type": "token", "text": text})

        abort = current_abort()
        try:
            if generator is not None:
                answer = generator(question, context)
                if not isinstance(answer, str) or not answer.strip():
                    logger.error(
                        "El generador devolvió una respuesta vacía o no textual."
                    )
                    return {"status": "error", "error": SAFE_ERROR_MESSAGE}
                outcome = GenerationOutcome(answer=answer.strip())
            else:
                generate = memory_generator or generate_with_memory
                outcome = generate(
                    question,
                    context,
                    memory_context,
                    **_supported_kwargs(
                        generate,
                        policy_correction=policy_correction,
                        conversation_history=conversation_history,
                        on_token=on_token,
                        abort=abort,
                    ),
                )
                if not isinstance(outcome, GenerationOutcome):
                    outcome = GenerationOutcome.model_validate(outcome)
        except GenerationAborted:
            raise
        except Exception:  # noqa: BLE001 - se reporta como fallo controlado
            logger.exception("Fallo al generar la respuesta RAG")
            return {"status": "error", "error": SAFE_ERROR_MESSAGE}

        answer = (outcome.answer or "").strip()
        if not answer:
            logger.error("El generador devolvió una respuesta vacía o no textual.")
            return {"status": "error", "error": SAFE_ERROR_MESSAGE}

        return {
            "answer": answer,
            "status": "ok",
            "error": None,
            "tool_context_included": tool_context is not None,
            "memory_proposal": _proposal_dict(outcome),
            "memory_validation_error": outcome.validation_error,
            "memory_used": answer_uses_memory(answer, memory_context),
        }

    return generate_node


def make_no_context_node(gate: MemoryGate | None = None):
    """Responde con honestidad; si hay memoria aprobada, la usa sin LLM."""

    memory_gate = gate or is_memory_candidate

    def no_context_node(state: AgentState) -> dict:
        memory_context = list(state.get("memory_context") or [])
        applicable = bool(memory_gate(state.get("question") or ""))
        if memory_context:
            return {
                "answer": answer_from_memory(memory_context),
                "status": "ok",
                "error": None,
                "memory_used": True,
                "memory_gate_applicable": applicable,
            }
        return {
            "answer": rag.NO_CONTEXT_ANSWER,
            "status": "no_context",
            "error": None,
            "memory_used": False,
            "memory_gate_applicable": applicable,
        }

    return no_context_node


no_context_node = make_no_context_node()


def make_memory_eval_node(evaluator: MemoryEvaluator | None = None):
    """Evalúa si una respuesta determinista debe generar una propuesta.

    Es la única llamada al LLM en esta ruta. Un fallo del evaluador nunca
    rompe la respuesta: se registra y se sigue sin propuesta.
    """

    evaluate = evaluator or evaluate_interaction

    def memory_eval_node(state: AgentState) -> dict:
        if state.get("status") == "error":
            return {}
        try:
            outcome = evaluate(
                question=state.get("question") or "",
                answer=state.get("answer") or "",
                tool_result=state.get("tool_result") or {},
                memory_context=list(state.get("memory_context") or []),
            )
            if not isinstance(outcome, EvaluationOutcome):
                outcome = EvaluationOutcome.model_validate(outcome)
        except Exception:  # noqa: BLE001 - la respuesta ya está construida
            logger.exception("Fallo al evaluar memoria en ruta determinista")
            return {
                "memory_proposal": None,
                "memory_validation_error": "evaluator_error",
            }

        return {
            "memory_proposal": _proposal_dict(outcome),
            "memory_validation_error": outcome.validation_error,
        }

    return memory_eval_node


memory_eval_node = make_memory_eval_node()


def route_after_memory_gate(state: AgentState) -> str:
    """Tras una respuesta determinista: evaluar memoria o terminar."""

    if state.get("status") == "error":
        return "end"
    return "memory_eval" if state.get("memory_gate_applicable") else "end"


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
    "MemoryEvaluator",
    "MemoryGate",
    "MemoryGenerator",
    "Retriever",
    "SAFE_ERROR_MESSAGE",
    "answer_from_tool_node",
    "fail_node",
    "make_answer_from_tool_node",
    "make_classify_node",
    "make_generate_node",
    "make_memory_eval_node",
    "make_no_context_node",
    "make_retrieve_node",
    "make_tool_incident_node",
    "make_tool_inventory_node",
    "memory_eval_node",
    "no_context_node",
    "receive_question",
    "route_after_memory_gate",
]
