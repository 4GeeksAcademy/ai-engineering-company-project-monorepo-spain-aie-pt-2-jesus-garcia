"""Runner del agente: ejecuta el grafo compilado y persiste una traza por corrida."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .graph import get_agent_graph
from .harness.orders import OrderResolver
from .harness.runtime import screen_input, validate_output
from .nodes import SAFE_ERROR_MESSAGE
from .streaming import GenerationAborted, TokenSink, bind_run, reset_run
from .tracing import (
    CheckpointRecord,
    TraceRecorder,
    summarize_payload,
)

logger = logging.getLogger(__name__)


class AgentRunError(RuntimeError):
    """La corrida del agente falló de forma no controlada."""


@dataclass(frozen=True)
class AgentResult:
    """Resultado mínimo que el endpoint puede devolver sin lógica propia."""

    run_id: str
    status: str
    answer: str
    error: str | None
    trace_path: str
    memory_proposal: dict | None = None
    memory_validation_error: str | None = None
    memory_gate: bool = False
    memory_used: bool = False
    guard_events: tuple[dict, ...] = ()


def _finish_guard(
    recorder: TraceRecorder,
    *,
    run_id: str,
    status: str,
    answer: str,
    error: str | None = None,
) -> AgentResult:
    trace = recorder.finish(status=status, answer=answer, error=error)
    trace_path = recorder.persist(trace)
    return AgentResult(
        run_id=run_id,
        status=status,
        answer=answer,
        error=error,
        trace_path=str(trace_path),
        guard_events=tuple(recorder.guard_events),
    )


def run_agent(
    question: str,
    *,
    graph: Any | None = None,
    trace_dir: str | Path | None = None,
    thread_id: str | None = None,
    run_id: str | None = None,
    user: dict | None = None,
    memory_context: list[dict] | None = None,
    session_id: str | None = None,
    order_resolver: OrderResolver | None = None,
    token_sink: TokenSink | None = None,
    abort: threading.Event | None = None,
    conversation_history: list[dict] | None = None,
) -> AgentResult:
    """Invoca el grafo, registra cada transición y escribe el trace en disco.

    ``thread_id`` es el hilo persistente del checkpointer; ``run_id`` identifica
    esta corrida concreta. En el chat son distintos: ``thread_id == session_id``
    y cada turno recibe un ``run_id`` nuevo.

    ``user`` es el usuario autenticado por el endpoint. Solo se propaga su rol
    al estado (nunca el token ni datos personales) para que la tool de tickets
    aplique la misma autorización que ``GET /api/incidents``.

    ``memory_context`` es el bloque acotado de memoria aprobada que el servicio
    leyó antes de la corrida. El grafo no accede a la base de datos.

    ``token_sink`` activa el streaming por LangGraph (``stream_mode="custom"``):
    cada token generado se entrega en vivo. ``abort`` detiene la generación de
    forma cooperativa y deja la corrida como ``interrupted``.

    El harness se ejecuta en este borde: ``screen_input`` antes del grafo y
    ``validate_output`` después. Un bloqueo o una respuesta determinista no
    invoca el LLM, el RAG ni las tools.
    """
    resolved_run_id = run_id or thread_id or str(uuid.uuid4())
    conversation_thread = thread_id or resolved_run_id
    trace_session = session_id or conversation_thread
    recorder = TraceRecorder(
        run_id=resolved_run_id,
        thread_id=conversation_thread,
        question=question,
        trace_dir=trace_dir,
    )

    guard = screen_input(
        question,
        user=user,
        run_id=resolved_run_id,
        session_id=trace_session,
        order_resolver=order_resolver,
    )
    recorder.record_guard_events(guard.events)

    if guard.action == "blocked":
        return _finish_guard(
            recorder,
            run_id=resolved_run_id,
            status="blocked",
            answer=guard.answer or SAFE_ERROR_MESSAGE,
        )
    if guard.action == "redirected":
        return _finish_guard(
            recorder,
            run_id=resolved_run_id,
            status="ok",
            answer=guard.answer or SAFE_ERROR_MESSAGE,
        )

    compiled = graph or get_agent_graph()
    config = {"configurable": {"thread_id": conversation_thread}}
    initial_state: dict[str, Any] = {
        "question": guard.question,
        "run_id": resolved_run_id,
        "session_id": trace_session,
        "memory_context": list(memory_context or []),
        "conversation_context": list(conversation_history or []),
    }
    if user and user.get("role"):
        initial_state["user_role"] = str(user["role"])
    correction = guard.context.get("policy_correction")
    if correction:
        initial_state["policy_correction"] = str(correction)

    context_tokens = bind_run(abort=abort, streaming=token_sink is not None)
    try:
        try:
            stream_mode: Any = (
                ["updates", "custom"]
                if token_sink is not None
                else "updates"
            )
            for chunk in compiled.stream(
                initial_state,
                config=config,
                stream_mode=stream_mode,
            ):
                if (
                    token_sink is not None
                    and isinstance(chunk, tuple)
                    and len(chunk) == 2
                ):
                    mode, payload = chunk
                    if mode == "custom":
                        if (
                            isinstance(payload, dict)
                            and payload.get("type") == "token"
                        ):
                            text = payload.get("text")
                            if isinstance(text, str) and text:
                                token_sink(text)
                        continue
                    chunk = payload
                if not isinstance(chunk, dict):
                    continue
                for node, update in chunk.items():
                    if not isinstance(node, str) or node.startswith("__"):
                        continue
                    recorder.record_node(
                        node,
                        update if isinstance(update, dict) else {},
                    )
            final_values = dict(compiled.get_state(config).values or {})
        except GenerationAborted:
            recorder.record_abort()
            trace = recorder.finish(
                status="interrupted",
                answer="",
                error=None,
            )
            trace_path = recorder.persist(trace)
            return AgentResult(
                run_id=resolved_run_id,
                status="interrupted",
                answer="",
                error=None,
                trace_path=str(trace_path),
                guard_events=tuple(recorder.guard_events),
            )
        except Exception as exc:  # noqa: BLE001 - se traza y se re-lanza controlado
            logger.exception("Fallo no controlado ejecutando el grafo del agente")
            recorder.record_failure(SAFE_ERROR_MESSAGE)
            recorder.attach_checkpoints(
                _checkpoint_history(compiled, config, len(recorder.events))
            )
            trace = recorder.finish(
                status="error",
                answer="",
                error=SAFE_ERROR_MESSAGE,
            )
            recorder.persist(trace)
            raise AgentRunError(SAFE_ERROR_MESSAGE) from exc
    finally:
        reset_run(context_tokens)

    recorder.attach_checkpoints(
        _checkpoint_history(compiled, config, len(recorder.events))
    )

    if abort is not None and abort.is_set():
        recorder.record_abort()
        trace = recorder.finish(
            status="interrupted",
            answer="",
            error=None,
        )
        trace_path = recorder.persist(trace)
        return AgentResult(
            run_id=resolved_run_id,
            status="interrupted",
            answer="",
            error=None,
            trace_path=str(trace_path),
            guard_events=tuple(recorder.guard_events),
        )

    status = str(final_values.get("status") or "error")
    answer = str(final_values.get("answer") or "")
    error = final_values.get("error")

    authorized_orders = guard.context.get("authorized_orders") or []
    authorized_refs = [
        str(order.get("order_ref"))
        for order in authorized_orders
        if isinstance(order, dict) and order.get("order_ref")
    ]
    output = None
    if status not in ("error", "invalid_question"):
        output = validate_output(
            answer,
            required_country=guard.context.get("required_country"),
            authorized_order_refs=authorized_refs,
            run_id=resolved_run_id,
            session_id=trace_session,
            question=guard.question,
        )
        if output.event is not None:
            recorder.record_guard_events([output.event])
        if output.action == "blocked":
            status = "blocked"
        answer = output.answer

    trace = recorder.finish(status=status, answer=answer, error=error)
    trace_path = recorder.persist(trace)

    return AgentResult(
        run_id=resolved_run_id,
        status=status,
        answer=answer,
        error=error,
        trace_path=str(trace_path),
        memory_proposal=(
            final_values.get("memory_proposal")
            if isinstance(final_values.get("memory_proposal"), dict)
            else None
        ),
        memory_validation_error=final_values.get("memory_validation_error"),
        memory_gate=bool(final_values.get("memory_gate_applicable")),
        memory_used=bool(final_values.get("memory_used")),
        guard_events=tuple(recorder.guard_events),
    )


def get_run_state(
    run_id: str,
    *,
    graph: Any | None = None,
) -> dict[str, Any]:
    """Estado más reciente guardado por el checkpointer para una corrida."""
    compiled = graph or get_agent_graph()
    snapshot = compiled.get_state({"configurable": {"thread_id": run_id}})
    return {
        "next": list(getattr(snapshot, "next", ()) or ()),
        "values": summarize_payload(dict(getattr(snapshot, "values", {}) or {})),
    }


def _checkpoint_history(
    compiled: Any,
    config: dict[str, Any],
    expected: int,
) -> list[CheckpointRecord]:
    """Snapshots del checkpointer, del más antiguo al más reciente.

    El historial incluye los checkpoints de entrada (START) además de uno por
    nodo ejecutado; se conservan los últimos ``expected`` para alinearlos con
    los eventos del trace.
    """
    try:
        snapshots = list(compiled.get_state_history(config))
    except Exception:  # noqa: BLE001 - un snapshot ausente no rompe la corrida
        return []

    records: list[CheckpointRecord] = []
    for snapshot in reversed(snapshots):
        snapshot_config = getattr(snapshot, "config", {}) or {}
        checkpoint_id = (snapshot_config.get("configurable") or {}).get(
            "checkpoint_id"
        )
        created_at = getattr(snapshot, "created_at", None)
        records.append(
            CheckpointRecord(
                step=0,
                checkpoint_id=checkpoint_id,
                next_nodes=list(getattr(snapshot, "next", ()) or ()),
                values=summarize_payload(
                    dict(getattr(snapshot, "values", {}) or {})
                ),
                created_at=str(created_at) if created_at is not None else None,
            )
        )

    if expected and len(records) > expected:
        records = records[-expected:]
    for step, record in enumerate(records):
        record.step = step
    return records


__all__ = ["AgentResult", "AgentRunError", "get_run_state", "run_agent"]
