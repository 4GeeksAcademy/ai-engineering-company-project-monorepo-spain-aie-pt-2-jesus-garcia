"""Runner del agente: ejecuta el grafo compilado y persiste una traza por corrida."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .graph import get_agent_graph
from .nodes import SAFE_ERROR_MESSAGE
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


def run_agent(
    question: str,
    *,
    graph: Any | None = None,
    trace_dir: str | Path | None = None,
    thread_id: str | None = None,
    user: dict | None = None,
) -> AgentResult:
    """Invoca el grafo, registra cada transición y escribe el trace en disco.

    ``thread_id`` es también el ``run_id``: el checkpointer guarda un snapshot
    por superstep y permite inspeccionar o retomar la corrida con
    ``graph.get_state`` / ``graph.get_state_history``.

    ``user`` es el usuario autenticado por el endpoint. Solo se propaga su rol
    al estado (nunca el token ni datos personales) para que la tool de tickets
    aplique la misma autorización que ``GET /api/incidents``.
    """
    compiled = graph or get_agent_graph()
    run_id = thread_id or str(uuid.uuid4())
    recorder = TraceRecorder(
        run_id=run_id,
        thread_id=run_id,
        question=question,
        trace_dir=trace_dir,
    )
    config = {"configurable": {"thread_id": run_id}}

    initial_state: dict[str, Any] = {"question": question, "run_id": run_id}
    if user and user.get("role"):
        initial_state["user_role"] = str(user["role"])

    try:
        for chunk in compiled.stream(
            initial_state,
            config=config,
            stream_mode="updates",
        ):
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

    recorder.attach_checkpoints(
        _checkpoint_history(compiled, config, len(recorder.events))
    )

    status = str(final_values.get("status") or "error")
    answer = str(final_values.get("answer") or "")
    error = final_values.get("error")
    trace = recorder.finish(status=status, answer=answer, error=error)
    trace_path = recorder.persist(trace)

    return AgentResult(
        run_id=run_id,
        status=status,
        answer=answer,
        error=error,
        trace_path=str(trace_path),
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
