"""Ejecución de la Parte 3: arbitraje, pausas, reanudación y cierre."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from data.pipelines.rfp_intake.llm import LlmClient
from data.pipelines.rfp_proposal.generators import generator_for
from data.pipelines.rfp_proposal.handoff import SECTION_NEEDS_REVIEW, SECTION_PASSED
from data.pipelines.rfp_proposal.section_graph import (
    DEFAULT_MAX_ITERATIONS,
    build_section_graph,
)

from .approval_graph import build_approval_branch_graph
from .arbitration_graph import build_arbitration_graph
from .contracts import (
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    TICKET_AWAITING,
    TICKET_FINISHED,
    TICKET_NEEDS_REVIEW,
    ApprovalStateError,
    briefs_from_intake,
    expected_currency,
    fallback_brief,
    normalize_intake,
    normalize_proposal,
    proposal_sections,
    validate_decision,
)
from .finalize_graph import build_finalize_graph
from .trace import compact, utc_now

logger = logging.getLogger(__name__)


class ApprovalPipelineError(RuntimeError):
    """Fallo controlado del flujo de aprobación."""


def repo_root() -> Path:
    configured = os.getenv("RFP_REPO_ROOT")
    if configured:
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "pipelines").is_dir():
            return parent
    return Path.cwd()


def approval_checkpoint_path() -> Path:
    configured = os.getenv("RFP_APPROVAL_CHECKPOINT_DB")
    if configured:
        return Path(configured)
    return repo_root() / "data" / "runtime" / "rfp-approval" / "checkpoints.db"


def _trace_dir() -> Path:
    configured = os.getenv("RFP_APPROVAL_TRACE_DIR")
    if configured:
        return Path(configured)
    return repo_root() / "data" / "eval" / "rfp-approval-traces"


def max_rounds_from_env() -> int:
    try:
        return max(1, int(os.getenv("RFP_APPROVAL_MAX_ROUNDS", "2")))
    except ValueError:
        return 2


def max_iterations_from_env() -> int:
    try:
        return max(1, int(os.getenv("RFP_PROPOSAL_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS)))
    except ValueError:
        return DEFAULT_MAX_ITERATIONS


def _append_trace(ticket_id: str, events: list[dict]) -> None:
    if not events:
        return
    try:
        directory = _trace_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{ticket_id}.json"
        existing: list[dict] = []
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                existing = list(payload.get("events") or [])
            except (OSError, ValueError):
                existing = []
        seen = {event.get("event_id") for event in existing}
        for event in events:
            if event.get("event_id") not in seen:
                existing.append(compact(event))
                seen.add(event.get("event_id"))
        path.write_text(
            json.dumps(
                {
                    "ticket_id": ticket_id,
                    "updated_at": utc_now(),
                    "events": existing,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
    except OSError as exc:  # pragma: no cover - la traza no debe tumbar el job
        logger.warning("No se pudo escribir la traza de aprobación %s: %s", ticket_id, exc)


def _flush_trace(repo, ticket_id: str, events: list[dict], *, thread_id: str) -> None:
    if not events:
        return
    try:
        repo.record_trace(ticket_id, events, thread_id=thread_id)
    except Exception:  # pragma: no cover - la traza no debe tumbar el job
        logger.exception("No se pudo persistir la traza de %s", ticket_id)
    _append_trace(ticket_id, events)


@contextmanager
def _checkpointer(provided=None) -> Iterator[object]:
    if provided is not None:
        yield provided
        return
    backend = os.getenv("RFP_APPROVAL_CHECKPOINT_BACKEND", "sqlite").lower()
    if backend == "memory":
        yield InMemorySaver()
        return
    path = approval_checkpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver


def _context(repo, ticket_id: str) -> dict:
    ticket = repo.get_ticket(ticket_id)
    proposal = normalize_proposal(
        repo.get_proposal(ticket_id) or ticket.get("proposal_payload"),
        ticket_id=ticket_id,
    )
    intake = normalize_intake(
        repo.get_intake_handoff(ticket_id), ticket_id=ticket_id
    )
    sections = repo.get_sections(ticket_id) or proposal_sections(proposal)
    if not sections:
        raise ApprovalStateError("La propuesta no tiene secciones activas.")
    return {
        "ticket": ticket,
        "proposal": proposal,
        "intake": intake,
        "sections": sections,
        "briefs": briefs_from_intake(intake),
        "currency": expected_currency(intake, proposal),
    }


def _real_regenerator(*, repo, llm, max_iterations: int, context: dict):
    def regenerate(
        ticket_id: str,
        department_id: str,
        section: dict,
        feedback: str,
        round_no: int,
    ) -> dict:
        brief = context["briefs"].get(department_id) or fallback_brief(
            section,
            proposal=context["proposal"],
            intake=context.get("intake") or {},
        )
        graph = build_section_graph(
            repo=repo,
            llm=llm,
            generator=generator_for(department_id),
            max_iterations=max_iterations,
        )
        result = graph.invoke(
            {
                "ticket_id": ticket_id,
                "brief": brief,
                "draft": section.get("draft_payload") or None,
                "result": {"feedback_for_generator": feedback},
                "iteration": int(section.get("iteration_count") or 0),
                "max_iterations": max_iterations,
                "evaluations": {},
                "events": [],
            },
            config={"recursion_limit": 60},
        )
        draft = result.get("draft") or {}
        evaluation = result.get("result") or {}
        passed = bool(evaluation.get("overall_pass"))
        status = result.get("status") or (
            SECTION_PASSED if passed else SECTION_NEEDS_REVIEW
        )
        return {
            **section,
            **draft,
            "evaluation_results": evaluation,
            "status": status,
            "iteration_count": result.get("iteration")
            or section.get("iteration_count"),
            "needs_human_review": status == SECTION_NEEDS_REVIEW,
            "provisional": status == SECTION_NEEDS_REVIEW,
            "review_reason": (
                evaluation.get("feedback_for_generator")
                if status == SECTION_NEEDS_REVIEW
                else None
            ),
            "approval_status": APPROVAL_PENDING,
            "approval_round": round_no,
        }

    return regenerate


def _interrupts(result: dict) -> list[tuple[str, dict]]:
    interrupts = result.get("__interrupt__") or []
    payloads: list[tuple[str, dict]] = []
    for item in interrupts:
        value = getattr(item, "value", None)
        interrupt_id = getattr(item, "id", None)
        if isinstance(value, dict) and interrupt_id:
            payloads.append((interrupt_id, value))
    return payloads


def _save_interrupts(repo, ticket_id: str, interrupts: list[tuple[str, dict]]) -> list[dict]:
    pending: list[dict] = []
    for interrupt_id, packet in interrupts:
        department_id = packet.get("department_id")
        if not department_id:
            continue
        repo.save_interrupt(
            ticket_id,
            department_id=department_id,
            interrupt_id=interrupt_id,
            packet=packet,
        )
        pending.append({**packet, "interrupt_id": interrupt_id})
    return pending


def _summary(repo, ticket_id: str, *, max_rounds: int) -> dict:
    ticket = repo.get_ticket(ticket_id)
    sections = repo.get_sections(ticket_id)
    pending = [
        {
            **(section.get("approval_packet") or {}),
            "interrupt_id": section.get("approval_interrupt_id"),
            "approval_status": section.get("approval_status"),
        }
        for section in sections.values()
        if section.get("approval_status") == APPROVAL_PENDING
        and section.get("approval_interrupt_id")
    ]
    decisions = [
        {
            "department_id": section.get("department_id"),
            "department_label": section.get("department_label"),
            "responsible": section.get("responsible"),
            "approval_status": section.get("approval_status"),
            "approver": section.get("approver"),
            "approved_at": section.get("approved_at"),
            "approval_comment": section.get("approval_comment"),
            "provisional": bool(section.get("provisional")),
        }
        for section in sections.values()
        if section.get("approval_status") in {APPROVAL_APPROVED, APPROVAL_REJECTED}
    ]
    return {
        "ticket_id": ticket_id,
        "rfp_id": ticket.get("rfp_id"),
        "status": ticket.get("status"),
        "approval_status": ticket.get("approval_status"),
        "thread_id": ticket.get("approval_thread_id"),
        "run": ticket.get("approval_run"),
        "max_rounds": max_rounds,
        "pending": pending,
        "decisions": decisions,
        "final_document_ready": ticket.get("status") == TICKET_FINISHED,
    }


def _initialise_sections(repo, ticket_id: str, sections: dict[str, dict]) -> dict[str, dict]:
    initialised: dict[str, dict] = {}
    for department_id, section in sections.items():
        updated = {
            **section,
            "approval_status": APPROVAL_PENDING,
            "approver": None,
            "approved_at": None,
            "approval_comment": None,
            "approval_round": 0,
            "approval_interrupt_id": None,
            "approval_packet": None,
            "provisional": bool(section.get("provisional")),
        }
        repo.save_section_snapshot(ticket_id, section=updated)
        initialised[department_id] = updated
    return initialised


def _run_finalize(repo, ticket_id: str) -> dict:
    graph = build_finalize_graph(repo=repo)
    result = graph.invoke(
        {"ticket_id": ticket_id, "events": []},
        config={"recursion_limit": 30},
    )
    _flush_trace(repo, ticket_id, result.get("events") or [], thread_id="finalize")
    return result


def maybe_finalize(repo, ticket_id: str) -> dict:
    sections = repo.get_sections(ticket_id)
    if any(
        section.get("approval_status") == APPROVAL_PENDING for section in sections.values()
    ):
        repo.set_approval_ticket_status(
            ticket_id, TICKET_AWAITING, approval_status="pending", stage=TICKET_AWAITING
        )
        return {"status": TICKET_AWAITING, "final_document": None}
    if any(
        section.get("approval_status") == APPROVAL_REJECTED for section in sections.values()
    ):
        repo.set_approval_ticket_status(
            ticket_id,
            TICKET_NEEDS_REVIEW,
            approval_status="rejected",
            stage=TICKET_NEEDS_REVIEW,
        )
        return {"status": TICKET_NEEDS_REVIEW, "final_document": None}
    result = _run_finalize(repo, ticket_id)
    return {
        "status": result.get("status"),
        "final_document": result.get("final_document"),
    }


def start_approval_flow(
    ticket_id: str,
    repo,
    *,
    llm=None,
    max_rounds: int | None = None,
    max_iterations: int | None = None,
    checkpointer=None,
    force_new_run: bool = False,
    regenerate=None,
) -> dict:
    """Crea el run de aprobaciones y pausa cada rama activa."""

    limit = max_rounds or max_rounds_from_env()
    context = _context(repo, ticket_id)
    ticket = context["ticket"]
    if ticket.get("status") == TICKET_FINISHED and not force_new_run:
        return _summary(repo, ticket_id, max_rounds=limit)
    if (
        not force_new_run
        and ticket.get("approval_status") in {"pending", "resuming"}
        and ticket.get("approval_thread_id")
    ):
        existing = _summary(repo, ticket_id, max_rounds=limit)
        if existing["pending"]:
            return existing
        sections = repo.get_sections(ticket_id)
        if sections and all(
            section.get("approval_status") == APPROVAL_APPROVED
            for section in sections.values()
        ):
            finalized = maybe_finalize(repo, ticket_id)
            summary = _summary(repo, ticket_id, max_rounds=limit)
            summary["final_document_ready"] = bool(
                finalized.get("final_document")
            )
            return summary
        if any(
            section.get("approval_status") == APPROVAL_REJECTED
            for section in sections.values()
        ):
            repo.set_approval_ticket_status(
                ticket_id,
                TICKET_NEEDS_REVIEW,
                approval_status="rejected",
                stage=TICKET_NEEDS_REVIEW,
            )
            return _summary(repo, ticket_id, max_rounds=limit)

    run_no = int(ticket.get("approval_run") or 0) + 1
    base_thread = f"rfp-{ticket_id}:run-{run_no}"
    repo.begin_approval_run(ticket_id, thread_id=base_thread, run=run_no)
    sections = _initialise_sections(
        repo, ticket_id, context["sections"]
    )
    context["sections"] = sections
    client = llm or LlmClient()
    max_iter = max_iterations or max_iterations_from_env()
    regenerate = regenerate or _real_regenerator(
        repo=repo, llm=client, max_iterations=max_iter, context=context
    )

    with _checkpointer(checkpointer) as saver:
        arbitration = build_arbitration_graph(
            repo=repo,
            regenerate=regenerate,
            max_rounds=limit,
        )
        arbitration_result = arbitration.invoke(
            {"ticket_id": ticket_id, "events": []},
            config={"recursion_limit": 50},
        )
        _flush_trace(
            repo,
            ticket_id,
            arbitration_result.get("events") or [],
            thread_id=base_thread,
        )
        if arbitration_result.get("status") == TICKET_NEEDS_REVIEW:
            repo.set_approval_ticket_status(
                ticket_id,
                TICKET_NEEDS_REVIEW,
                approval_status="rejected",
                stage=TICKET_NEEDS_REVIEW,
            )
            return _summary(repo, ticket_id, max_rounds=limit)

        sections = arbitration_result.get("sections") or repo.get_sections(ticket_id)
        conflicts = arbitration_result.get("conflicts") or []
        context["sections"] = sections
        context["conflicts"] = conflicts

        for department_id in list(sections):
            section = sections[department_id]
            if section.get("approval_status") in {APPROVAL_APPROVED, APPROVAL_REJECTED}:
                continue
            branch_thread = f"{base_thread}:{department_id}"
            branch = build_approval_branch_graph(
                repo=repo,
                regenerate=regenerate,
                checkpointer=saver,
                max_rounds=limit,
            )
            branch_result = branch.invoke(
                {
                    "ticket_id": ticket_id,
                    "thread_id": branch_thread,
                    "department_id": department_id,
                    "section": section,
                    "context": {
                        "proposal": context["proposal"],
                        "intake": context.get("intake") or {},
                        "brief": context["briefs"].get(department_id),
                        "conflicts": conflicts,
                        "max_rounds": limit,
                    },
                    "approval_round": int(section.get("approval_round") or 0),
                    "max_rounds": limit,
                    "events": [],
                },
                config={
                    "configurable": {"thread_id": branch_thread},
                    "recursion_limit": 40,
                },
            )
            _flush_trace(
                repo,
                ticket_id,
                branch_result.get("events") or [],
                thread_id=branch_thread,
            )
            pending = _save_interrupts(repo, ticket_id, _interrupts(branch_result))
            if not pending and branch_result.get("status") in {
                APPROVAL_APPROVED,
                APPROVAL_REJECTED,
            }:
                logger.info(
                    "rfp_approval rama %s terminó sin interrupt (%s)",
                    department_id,
                    branch_result.get("status"),
                )

    finalized = maybe_finalize(repo, ticket_id)
    summary = _summary(repo, ticket_id, max_rounds=limit)
    summary["final_document_ready"] = bool(finalized.get("final_document"))
    return summary


def resume_approval(
    ticket_id: str,
    department_id: str,
    decision: dict,
    repo,
    *,
    llm=None,
    max_rounds: int | None = None,
    max_iterations: int | None = None,
    checkpointer=None,
    regenerate=None,
) -> dict:
    """Reanuda exactamente la rama interrumpida; no reinicia el flujo."""

    limit = max_rounds or max_rounds_from_env()
    context = _context(repo, ticket_id)
    ticket = context["ticket"]
    if ticket.get("status") != TICKET_AWAITING:
        raise ApprovalStateError(
            "El ticket no está esperando aprobación "
            f"(status={ticket.get('status')!r})."
        )
    section = context["sections"].get(department_id)
    if section is None:
        raise ApprovalStateError(
            f"El departamento {department_id!r} no está activo en este ticket."
        )
    if section.get("approval_status") != APPROVAL_PENDING:
        raise ApprovalStateError(
            "La sección no tiene una aprobación pendiente "
            f"(approval_status={section.get('approval_status')!r})."
        )
    expected_interrupt = section.get("approval_interrupt_id")
    if not expected_interrupt:
        raise ApprovalStateError(
            "La aprobación no tiene interrupt_id persistido; reinicia el flujo."
        )
    if (decision or {}).get("interrupt_id") and decision["interrupt_id"] != expected_interrupt:
        raise ApprovalStateError(
            "La decisión no corresponde al interrupt pendiente de esta sección."
        )
    validated = validate_decision(decision, section=section, max_rounds=limit)
    validated["interrupt_id"] = expected_interrupt

    base_thread = ticket.get("approval_thread_id")
    if not base_thread:
        raise ApprovalStateError(
            "El ticket no tiene thread de aprobación; reinicia el flujo."
        )
    branch_thread = f"{base_thread}:{department_id}"
    repo.set_approval_ticket_status(
        ticket_id, TICKET_AWAITING, approval_status="resuming", stage="aprobando"
    )
    client = llm or LlmClient()
    max_iter = max_iterations or max_iterations_from_env()
    regenerate = regenerate or _real_regenerator(
        repo=repo, llm=client, max_iterations=max_iter, context=context
    )

    with _checkpointer(checkpointer) as saver:
        branch = build_approval_branch_graph(
            repo=repo,
            regenerate=regenerate,
            checkpointer=saver,
            max_rounds=limit,
        )
        branch_result = branch.invoke(
            Command(resume={expected_interrupt: validated}),
            config={
                "configurable": {"thread_id": branch_thread},
                "recursion_limit": 40,
            },
        )
        _flush_trace(
            repo,
            ticket_id,
            branch_result.get("events") or [],
            thread_id=branch_thread,
        )
        pending = _save_interrupts(repo, ticket_id, _interrupts(branch_result))

    if pending:
        repo.set_approval_ticket_status(
            ticket_id, TICKET_AWAITING, approval_status="pending", stage=TICKET_AWAITING
        )
        summary = _summary(repo, ticket_id, max_rounds=limit)
        summary["final_document_ready"] = False
        return summary

    finalized = maybe_finalize(repo, ticket_id)
    summary = _summary(repo, ticket_id, max_rounds=limit)
    summary["final_document_ready"] = bool(finalized.get("final_document"))
    return summary


__all__ = [
    "ApprovalPipelineError",
    "approval_checkpoint_path",
    "maybe_finalize",
    "resume_approval",
    "start_approval_flow",
]
