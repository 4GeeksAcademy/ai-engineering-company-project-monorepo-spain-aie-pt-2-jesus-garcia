"""Fixtures compartidas por los tests del pipeline ``rfp_approval``."""

from __future__ import annotations

import copy

from rfp_proposal_support import (
    InMemoryProposalRepo,
    ScriptedProposalLlm,
    luna_handoff,
    modaviva_handoff,
    prose,
    run_proposal,
)
from data.pipelines.rfp_approval.contracts import (
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    TICKET_AWAITING,
)


def _generators(handoff: dict) -> dict[str, dict]:
    return {
        department["department_id"]: prose(
            aspects=[aspect["aspect"] for aspect in department["key_aspects"]]
        )
        for department in handoff["departments"]
    }


def build_proposal(
    handoff: dict, *, ticket_id: str | None = None
) -> tuple[dict, dict]:
    """Ejecuta la Parte 2 con un LLM guionizado y devuelve (proposal, intake)."""

    ticket = ticket_id or handoff.get("ticket_id") or "ticket-1"
    llm = ScriptedProposalLlm(generators=_generators(handoff))
    repo = InMemoryProposalRepo(handoff, ticket_id=ticket)
    repo, _ = run_proposal(handoff, llm=llm, repo=repo, max_iterations=2)
    return copy.deepcopy(repo.proposal_handoff), copy.deepcopy(handoff)


class InMemoryApprovalRepo:
    def __init__(
        self,
        *,
        proposal: dict,
        intake: dict,
        ticket_id: str | None = None,
    ) -> None:
        self.ticket = {
            "ticket_id": ticket_id or proposal.get("ticket_id") or "ticket-1",
            "rfp_id": proposal.get("rfp_id") or intake.get("rfp_id"),
            "status": TICKET_AWAITING,
            "proposal_status": TICKET_AWAITING,
            "proposal_payload": copy.deepcopy(proposal),
            "handoff_payload": copy.deepcopy(intake),
            "approval_status": None,
            "approval_thread_id": None,
            "approval_run": 0,
            "approval_started_at": None,
            "approval_completed_at": None,
            "approval_error": None,
        }
        self.proposal = copy.deepcopy(proposal)
        self.intake = copy.deepcopy(intake)
        self.sections: dict[str, dict] = {}
        for section in proposal.get("sections") or []:
            department_id = section["department_id"]
            self.sections[department_id] = {
                **copy.deepcopy(section),
                "approval_status": section.get("approval_status")
                or APPROVAL_PENDING,
                "approver": None,
                "approved_at": None,
                "approval_comment": None,
                "approval_round": 0,
                "approval_interrupt_id": None,
                "approval_packet": None,
            }
        self.final_document: dict | None = None
        self.final_path: str | None = None
        self.traces: list[dict] = []
        self.arbitrations: list[dict] = []
        self.failure: dict = {}

    def get_ticket(self, ticket_id: str) -> dict:
        return copy.deepcopy(self.ticket)

    def get_proposal(self, ticket_id: str) -> dict | None:
        return copy.deepcopy(self.proposal)

    def get_intake_handoff(self, ticket_id: str) -> dict | None:
        return copy.deepcopy(self.intake)

    def get_rfp_facts(self, ticket_id: str) -> dict:
        return copy.deepcopy((self.intake or {}).get("rfp_facts") or {})

    def get_sections(self, ticket_id: str) -> dict[str, dict]:
        return copy.deepcopy(self.sections)

    def begin_approval_run(self, ticket_id: str, *, thread_id: str, run: int) -> None:
        self.ticket.update(
            {
                "status": TICKET_AWAITING,
                "proposal_status": TICKET_AWAITING,
                "approval_status": "pending",
                "approval_thread_id": thread_id,
                "approval_run": run,
                "approval_started_at": "2026-11-15T12:00:00+00:00",
                "approval_completed_at": None,
                "approval_error": None,
            }
        )

    def set_approval_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        approval_status: str | None = None,
        stage: str | None = None,
        completed: bool = False,
    ) -> None:
        self.ticket["status"] = status
        self.ticket["proposal_status"] = status
        if approval_status is not None:
            self.ticket["approval_status"] = approval_status
        if completed:
            self.ticket["approval_completed_at"] = "2026-11-15T12:05:00+00:00"

    def set_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        stage: str | None = None,
        force: bool = False,
    ) -> None:
        self.ticket["status"] = status
        self.ticket["proposal_status"] = status

    def save_draft(
        self,
        ticket_id: str,
        *,
        department_id: str,
        draft: dict,
        iteration: int,
    ) -> None:
        section = self.sections.setdefault(department_id, {})
        section["draft_content"] = draft.get("body_markdown")
        section["draft_payload"] = copy.deepcopy(draft)
        section["iteration_count"] = iteration

    def save_evaluation(
        self,
        ticket_id: str,
        *,
        department_id: str,
        evaluation: dict,
    ) -> None:
        section = self.sections.setdefault(department_id, {})
        section["evaluation_results"] = copy.deepcopy(evaluation)
        section["iteration_count"] = int(evaluation.get("iteration") or 1)

    def save_section_status(
        self,
        ticket_id: str,
        *,
        department_id: str,
        status: str,
        review_reason: str | None = None,
    ) -> None:
        section = self.sections.setdefault(department_id, {})
        section["generation_status"] = status
        if review_reason:
            section["review_reason"] = review_reason

    def save_approval_packet(
        self,
        ticket_id: str,
        *,
        department_id: str,
        packet: dict,
        approval_round: int,
    ) -> None:
        section = self.sections.setdefault(department_id, {})
        section["approval_status"] = APPROVAL_PENDING
        section["approval_packet"] = copy.deepcopy(packet)
        section["approval_round"] = approval_round

    def save_approval_decision(
        self,
        ticket_id: str,
        *,
        department_id: str,
        status: str,
        approver: str | None,
        comment: str | None,
        decided_at: str | None,
        approval_round: int,
    ) -> None:
        section = self.sections.setdefault(department_id, {})
        section["approval_status"] = status
        section["approver"] = approver
        section["approval_comment"] = comment
        section["approval_round"] = approval_round
        if status == APPROVAL_APPROVED:
            section["approved_at"] = decided_at
        else:
            section["approved_at"] = None
            section["review_reason"] = comment
        section["approval_interrupt_id"] = None

    def save_interrupt(
        self,
        ticket_id: str,
        *,
        department_id: str,
        interrupt_id: str,
        packet: dict,
    ) -> None:
        section = self.sections.setdefault(department_id, {})
        section["approval_status"] = APPROVAL_PENDING
        section["approval_interrupt_id"] = interrupt_id
        section["approval_packet"] = copy.deepcopy(packet)

    def save_section_snapshot(self, ticket_id: str, *, section: dict) -> None:
        department_id = section.get("department_id")
        if not department_id:
            return
        self.sections[department_id] = {
            **self.sections.get(department_id, {}),
            **copy.deepcopy(section),
        }

    def record_trace(self, ticket_id: str, events: list[dict], *, thread_id: str) -> None:
        seen = {event.get("event_id") for event in self.traces}
        for event in events:
            if event.get("event_id") not in seen:
                self.traces.append({**copy.deepcopy(event), "thread_id": thread_id})
                seen.add(event.get("event_id"))

    def record_arbitration(
        self,
        ticket_id: str,
        *,
        round: int,
        conflict: dict,
        resolution: dict,
    ) -> None:
        self.arbitrations.append(
            {
                "round": round,
                "conflict": copy.deepcopy(conflict),
                "resolution": copy.deepcopy(resolution),
            }
        )

    def save_final_document(self, ticket_id: str, *, document: dict, path: str | None = None) -> str | None:
        self.final_document = copy.deepcopy(document)
        self.final_path = path or f"/tmp/{ticket_id}/propuesta-final.md"
        return self.final_path

    def fail(self, ticket_id: str, *, stage: str, error: str) -> None:
        self.failure = {"stage": stage, "error": error}
        self.ticket["status"] = "error"


def fake_regenerate(
    *,
    mutate=None,
):
    """Regeneración simulada: aplica un cambio y devuelve evaluación limpia."""

    def regenerate(
        ticket_id: str,
        department_id: str,
        section: dict,
        feedback: str,
        round_no: int,
    ) -> dict:
        updated = copy.deepcopy(section)
        if mutate is not None:
            updated = mutate(updated, feedback, round_no)
        updated.setdefault("department_id", department_id)
        updated["iteration_count"] = int(updated.get("iteration_count") or 0) + 1
        updated["evaluation_results"] = {
            "overall_pass": True,
            "readability": {"pass": True},
            "relevance": {"pass": True},
            "compliance": {
                "pass": True,
                "rule_ids": [],
                "violations": [],
            },
        }
        updated["review_reason"] = None
        updated["needs_human_review"] = False
        updated["approval_status"] = APPROVAL_PENDING
        updated["approval_round"] = round_no
        return updated

    return regenerate


def proposal_for_modaviva(ticket_id: str = "ticket-1") -> tuple[dict, dict]:
    return build_proposal(modaviva_handoff(ticket_id), ticket_id=ticket_id)


def proposal_for_luna(ticket_id: str = "ticket-2") -> tuple[dict, dict]:
    return build_proposal(luna_handoff(ticket_id), ticket_id=ticket_id)


def pending_for(repo: InMemoryApprovalRepo, department_id: str) -> dict:
    section = repo.sections[department_id]
    return {
        **section["approval_packet"],
        "interrupt_id": section["approval_interrupt_id"],
    }


def decision(
    *,
    action: str,
    approver: str,
    interrupt_id: str,
    comment: str | None = None,
    acknowledge_provisional: bool = False,
) -> dict:
    return {
        "action": action,
        "approver": approver,
        "interrupt_id": interrupt_id,
        "comment": comment,
        "acknowledge_provisional": acknowledge_provisional,
    }


__all__ = [
    "InMemoryApprovalRepo",
    "build_proposal",
    "decision",
    "fake_regenerate",
    "pending_for",
    "proposal_for_luna",
    "proposal_for_modaviva",
]
