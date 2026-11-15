"""Puerto de persistencia de la Parte 3 (sin SQLModel en el pipeline)."""

from __future__ import annotations

from typing import Protocol


class ApprovalRepository(Protocol):
    # --- ticket / contexto -------------------------------------------------
    def get_ticket(self, ticket_id: str) -> dict: ...

    def get_proposal(self, ticket_id: str) -> dict | None: ...

    def get_intake_handoff(self, ticket_id: str) -> dict | None: ...

    def get_rfp_facts(self, ticket_id: str) -> dict: ...

    def get_sections(self, ticket_id: str) -> dict[str, dict]: ...

    def begin_approval_run(
        self,
        ticket_id: str,
        *,
        thread_id: str,
        run: int,
    ) -> None: ...

    def set_approval_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        approval_status: str | None = None,
        stage: str | None = None,
        completed: bool = False,
    ) -> None: ...

    # --- sección (compatible con el subgrafo de la Parte 2) ----------------
    def set_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        stage: str | None = None,
        force: bool = False,
    ) -> None: ...

    def save_draft(
        self,
        ticket_id: str,
        *,
        department_id: str,
        draft: dict,
        iteration: int,
    ) -> None: ...

    def save_evaluation(
        self,
        ticket_id: str,
        *,
        department_id: str,
        evaluation: dict,
    ) -> None: ...

    def save_section_status(
        self,
        ticket_id: str,
        *,
        department_id: str,
        status: str,
        review_reason: str | None = None,
    ) -> None: ...

    # --- aprobación --------------------------------------------------------
    def save_approval_packet(
        self,
        ticket_id: str,
        *,
        department_id: str,
        packet: dict,
        approval_round: int,
    ) -> None: ...

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
    ) -> None: ...

    def save_interrupt(
        self,
        ticket_id: str,
        *,
        department_id: str,
        interrupt_id: str,
        packet: dict,
    ) -> None: ...

    def save_section_snapshot(
        self,
        ticket_id: str,
        *,
        section: dict,
    ) -> None: ...

    def record_trace(
        self,
        ticket_id: str,
        events: list[dict],
        *,
        thread_id: str,
    ) -> None: ...

    def record_arbitration(
        self,
        ticket_id: str,
        *,
        round: int,
        conflict: dict,
        resolution: dict,
    ) -> None: ...

    def save_final_document(
        self,
        ticket_id: str,
        *,
        document: dict,
        path: str | None = None,
    ) -> str | None: ...


__all__ = ["ApprovalRepository"]
