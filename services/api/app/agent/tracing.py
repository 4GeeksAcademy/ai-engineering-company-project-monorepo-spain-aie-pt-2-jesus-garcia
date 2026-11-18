"""Trazas estructuradas del agente, consultables después de cada corrida.

Cada ``run_agent`` escribe un JSON con la pregunta, el estado final, los nodos
ejecutados en orden, lo que produjo cada uno y los checkpoints intermedios.
También se añade una línea al índice ``index.jsonl`` del directorio de trazas
para poder localizar corridas sin conocer el ``run_id``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INDEX_FILENAME = "index.jsonl"
TRACE_DIR_ENV_VAR = "AGENT_TRACE_DIR"

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def resolve_trace_dir(trace_dir: str | Path | None = None) -> Path:
    """Directorio de trazas: argumento > ``AGENT_TRACE_DIR`` > ``data/eval``."""
    if trace_dir is not None:
        return Path(trace_dir)
    configured = os.getenv(TRACE_DIR_ENV_VAR)
    if configured:
        return Path(configured)
    try:
        repo_root = Path(__file__).resolve().parents[4]
        return repo_root / "data" / "eval" / "agent-traces"
    except IndexError:  # Docker: /app/app/agent/tracing.py
        return Path("/app") / "data" / "eval" / "agent-traces"


def summarize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Resume el estado para el trace sin perder el contexto recuperado.

    El contexto se guarda completo (documento, sección y texto) porque es lo
    que permite auditar el anclaje de la respuesta. El resto de campos se
    copian tal cual: son pocos y no contienen información sensible.
    """
    summary: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if key == "context":
            items = value if isinstance(value, list) else []
            summary["context_count"] = len(items)
            summary["sources"] = [
                {
                    "source_document": item.get("source_document"),
                    "section": item.get("section"),
                    "chunk_index": item.get("chunk_index"),
                    "text": item.get("text"),
                }
                for item in items
                if isinstance(item, dict)
            ]
            continue
        summary[key] = value
    return summary


@dataclass
class TraceEvent:
    """Un nodo ejecutado y su efecto sobre el estado."""

    seq: int
    node: str
    at: str
    elapsed_ms: float
    output: dict[str, Any] = field(default_factory=dict)
    checkpoint_id: str | None = None
    next_nodes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "node": self.node,
            "at": self.at,
            "elapsed_ms": self.elapsed_ms,
            "checkpoint_id": self.checkpoint_id,
            "next_nodes": self.next_nodes,
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceEvent:
        return cls(
            seq=int(data.get("seq", 0)),
            node=str(data.get("node", "")),
            at=str(data.get("at", "")),
            elapsed_ms=float(data.get("elapsed_ms", 0.0)),
            output=dict(data.get("output") or {}),
            checkpoint_id=data.get("checkpoint_id"),
            next_nodes=list(data.get("next_nodes") or []),
        )


@dataclass
class CheckpointRecord:
    """Snapshot del estado tras una transición."""

    step: int
    checkpoint_id: str | None
    next_nodes: list[str]
    values: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "checkpoint_id": self.checkpoint_id,
            "next_nodes": self.next_nodes,
            "values": self.values,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointRecord:
        return cls(
            step=int(data.get("step", 0)),
            checkpoint_id=data.get("checkpoint_id"),
            next_nodes=list(data.get("next_nodes") or []),
            values=dict(data.get("values") or {}),
            created_at=data.get("created_at"),
        )


@dataclass
class AgentTrace:
    """Artefacto completo de una corrida del agente."""

    run_id: str
    thread_id: str
    question: str
    status: str
    answer: str
    error: str | None
    started_at: str
    finished_at: str
    duration_ms: float
    events: list[TraceEvent] = field(default_factory=list)
    checkpoints: list[CheckpointRecord] = field(default_factory=list)
    trace_path: str | None = None

    @property
    def node_order(self) -> list[str]:
        return [event.node for event in self.events]

    @property
    def retrieved_sources(self) -> list[dict[str, Any]]:
        for event in reversed(self.events):
            if event.node == "retrieve":
                return list(event.output.get("sources") or [])
        return []

    @property
    def retrieved_texts(self) -> list[str]:
        return [
            str(source.get("text"))
            for source in self.retrieved_sources
            if source.get("text") is not None
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "thread_id": self.thread_id,
            "question": self.question,
            "status": self.status,
            "answer": self.answer,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "node_order": self.node_order,
            "events": [event.to_dict() for event in self.events],
            "checkpoints": [record.to_dict() for record in self.checkpoints],
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], *, trace_path: str | None = None
    ) -> AgentTrace:
        return cls(
            run_id=str(data.get("run_id", "")),
            thread_id=str(data.get("thread_id", data.get("run_id", ""))),
            question=str(data.get("question", "")),
            status=str(data.get("status", "error")),
            answer=str(data.get("answer", "")),
            error=data.get("error"),
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at", "")),
            duration_ms=float(data.get("duration_ms", 0.0)),
            events=[
                TraceEvent.from_dict(event) for event in data.get("events") or []
            ],
            checkpoints=[
                CheckpointRecord.from_dict(record)
                for record in data.get("checkpoints") or []
            ],
            trace_path=trace_path,
        )

    @classmethod
    def load(cls, path: str | Path) -> AgentTrace:
        trace_path = Path(path)
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        return cls.from_dict(data, trace_path=str(trace_path))

    @classmethod
    def load_latest(cls, directory: str | Path | None = None) -> AgentTrace:
        trace_dir = resolve_trace_dir(directory)
        files = sorted(
            trace_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
        )
        if not files:
            raise FileNotFoundError(f"No hay traces en {trace_dir}")
        return cls.load(files[-1])


class TraceRecorder:
    """Acumula eventos y checkpoints y los persiste como JSON."""

    def __init__(
        self,
        *,
        run_id: str,
        thread_id: str,
        question: str,
        trace_dir: str | Path | None = None,
    ) -> None:
        self.run_id = run_id
        self.thread_id = thread_id
        self.question = question
        self.trace_dir = resolve_trace_dir(trace_dir)
        self.started_at = utc_now()
        self.events: list[TraceEvent] = []
        self.checkpoints: list[CheckpointRecord] = []
        self._started_perf = time.perf_counter()
        self._last_perf = self._started_perf

    def record_node(
        self,
        node: str,
        update: dict[str, Any] | None,
    ) -> TraceEvent:
        now_perf = time.perf_counter()
        event = TraceEvent(
            seq=len(self.events),
            node=node,
            at=utc_now(),
            elapsed_ms=round((now_perf - self._last_perf) * 1000, 2),
            output=summarize_payload(update),
        )
        self._last_perf = now_perf
        self.events.append(event)
        return event

    def attach_checkpoints(self, records: list[CheckpointRecord]) -> None:
        """Alinea los snapshots del checkpointer con los nodos ya ejecutados."""
        for event, record in zip(self.events, records, strict=False):
            event.checkpoint_id = record.checkpoint_id
            event.next_nodes = list(record.next_nodes)
            self.checkpoints.append(record)


    def record_failure(self, message: str) -> None:
        """Deja constancia de un fallo no controlado sin filtrar el detalle."""
        event = TraceEvent(
            seq=len(self.events),
            node="<run>",
            at=utc_now(),
            elapsed_ms=round((time.perf_counter() - self._last_perf) * 1000, 2),
            output={"status": "error", "error": message},
        )
        self._last_perf = time.perf_counter()
        self.events.append(event)

    def finish(self, *, status: str, answer: str, error: str | None) -> AgentTrace:
        return AgentTrace(
            run_id=self.run_id,
            thread_id=self.thread_id,
            question=self.question,
            status=status,
            answer=answer,
            error=error,
            started_at=self.started_at,
            finished_at=utc_now(),
            duration_ms=round((time.perf_counter() - self._started_perf) * 1000, 2),
            events=list(self.events),
            checkpoints=list(self.checkpoints),
        )

    def persist(self, trace: AgentTrace) -> Path:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        safe_run_id = _SAFE_NAME_RE.sub("_", self.run_id) or "run"
        path = self.trace_dir / f"{safe_run_id}.json"
        path.write_text(
            json.dumps(trace.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        trace.trace_path = str(path)
        with (self.trace_dir / INDEX_FILENAME).open("a", encoding="utf-8") as index:
            index.write(
                json.dumps(
                    {
                        "run_id": self.run_id,
                        "thread_id": self.thread_id,
                        "question": self.question,
                        "status": trace.status,
                        "finished_at": trace.finished_at,
                        "trace_file": path.name,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return path


__all__ = [
    "AgentTrace",
    "CheckpointRecord",
    "TraceEvent",
    "TraceRecorder",
    "resolve_trace_dir",
    "summarize_payload",
    "utc_now",
]
