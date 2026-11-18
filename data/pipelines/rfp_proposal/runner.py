"""Ejecución del grafo ``rfp_proposal`` con traza y fallo durable."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from data.pipelines.rfp_intake.llm import JsonLlm, LlmClient

from .contract import HandoffContractError
from .graph import build_proposal_graph
from .section_graph import DEFAULT_MAX_ITERATIONS

logger = logging.getLogger(__name__)


class ProposalPipelineError(RuntimeError):
    """Fallo controlado de la generación de propuesta."""


def max_iterations_from_env() -> int:
    try:
        value = int(os.getenv("RFP_PROPOSAL_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS))
    except ValueError:
        return DEFAULT_MAX_ITERATIONS
    return max(1, value)


def _trace_dir() -> Path:
    configured = os.getenv("RFP_PROPOSAL_TRACE_DIR")
    if configured:
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "pipelines").is_dir():
            return parent / "data" / "eval" / "rfp-proposal-traces"
    return Path.cwd() / "data" / "eval" / "rfp-proposal-traces"


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


def run_proposal_generation(
    ticket_id: str,
    repo,
    *,
    llm: JsonLlm | None = None,
    max_iterations: int | None = None,
) -> dict:
    """Genera y evalúa las secciones de un ticket listo de la Parte 1."""

    client = llm or LlmClient()
    limit = max_iterations or max_iterations_from_env()
    graph = build_proposal_graph(
        repo=repo,
        llm=client,
        max_iterations=limit,
    )
    started_at = datetime.now(timezone.utc)

    try:
        result = graph.invoke(
            {
                "ticket_id": ticket_id,
                "sections": {},
                "events": [],
            },
            config={"recursion_limit": 80},
        )
    except HandoffContractError as exc:
        # No es un fallo técnico: el ticket no está listo o el contrato no
        # encaja. No se marca `error` para no corromper un análisis válido.
        _write_trace(
            ticket_id,
            {
                "ticket_id": ticket_id,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc),
                "status": "contract_error",
                "error": str(exc),
            },
        )
        raise ProposalPipelineError(str(exc)) from exc
    except Exception as exc:
        ticket = {}
        try:
            ticket = repo.get_ticket(ticket_id)
        except Exception:  # pragma: no cover - el ticket puede no existir
            pass
        stage = ticket.get("proposal_stage") or "generando_borrador"
        message = f"{type(exc).__name__}: {exc}"
        try:
            repo.fail(ticket_id, stage=stage, error=message)
        except Exception:  # pragma: no cover
            logger.exception(
                "No se pudo marcar el ticket %s como error", ticket_id
            )
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
        logger.exception(
            "rfp_proposal falló en ticket %s (stage=%s)", ticket_id, stage
        )
        raise ProposalPipelineError(f"{stage}: {message}") from exc

    _write_trace(
        ticket_id,
        {
            "ticket_id": ticket_id,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc),
            "status": result.get("status"),
            "state": {
                key: value
                for key, value in result.items()
                if key not in {"events"}
            },
        },
    )
    logger.info(
        "rfp_proposal ticket=%s status=%s max_iterations=%d",
        ticket_id,
        result.get("status"),
        limit,
    )
    return result
