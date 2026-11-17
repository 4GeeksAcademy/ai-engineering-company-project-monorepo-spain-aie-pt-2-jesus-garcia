"""Ejecución del grafo ``rfp_intake`` con traza y marca de fallo durable."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .graph import Converter, build_rfp_graph
from .ingest import convert_pdf_to_markdown
from .llm import JsonLlm, LlmClient

logger = logging.getLogger(__name__)


class RfpPipelineError(RuntimeError):
    """Fallo controlado del pipeline, con el stage donde ocurrió."""


def _trace_dir() -> Path:
    configured = os.getenv("RFP_TRACE_DIR")
    if configured:
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "pipelines").is_dir():
            return parent / "data" / "eval" / "rfp-traces"
    return Path.cwd() / "data" / "eval" / "rfp-traces"


def _write_trace(ticket_id: str, payload: dict) -> None:
    try:
        directory = _trace_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{ticket_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as exc:  # pragma: no cover - la traza no debe tumbar el job
        logger.warning("No se pudo escribir la traza de %s: %s", ticket_id, exc)


def run_rfp_intake(
    ticket_id: str,
    repo,
    *,
    llm: JsonLlm | None = None,
    converter: Converter = convert_pdf_to_markdown,
) -> dict:
    """Ejecuta el pipeline completo y devuelve el estado final.

    Si un nodo falla, se persiste ``status=error`` + stage + mensaje y se
    relanza la excepción para que Celery aplique su política de reintentos.
    """

    client = llm or LlmClient()
    repo.mark_processing(ticket_id)
    started_at = datetime.now(timezone.utc)
    graph = build_rfp_graph(repo=repo, llm=client, converter=converter)

    try:
        result = graph.invoke(
            {
                "ticket_id": ticket_id,
                "status": "processing",
                "sections": {},
                "events": [],
            },
            config={"recursion_limit": 50},
        )
    except Exception as exc:
        ticket = {}
        try:
            ticket = repo.get_ticket(ticket_id)
        except Exception:  # pragma: no cover - el ticket puede no existir
            pass
        stage = ticket.get("pipeline_stage") or "desconocido"
        message = f"{type(exc).__name__}: {exc}"
        try:
            repo.fail(ticket_id, stage=stage, error=message)
        except Exception:  # pragma: no cover
            logger.exception("No se pudo marcar el ticket %s como error", ticket_id)
        _write_trace(
            ticket_id,
            {
                "ticket_id": ticket_id,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc),
                "status": "error",
                "stage": stage,
                "error": message,
            },
        )
        logger.exception("rfp_intake falló en ticket %s (stage=%s)", ticket_id, stage)
        raise RfpPipelineError(f"{stage}: {message}") from exc

    finished_at = datetime.now(timezone.utc)
    trace_state = {
        key: value for key, value in result.items() if key != "markdown"
    }
    _write_trace(
        ticket_id,
        {
            "ticket_id": ticket_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": result.get("status"),
            "state": trace_state,
        },
    )
    logger.info(
        "rfp_intake ticket=%s status=%s stage=%s",
        ticket_id,
        result.get("status"),
        result.get("stage"),
    )
    return result
