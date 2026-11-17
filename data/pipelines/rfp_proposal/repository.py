"""Puerto de persistencia de la Parte 2.

El pipeline no importa SQLModel: la API inyecta ``SqlRfpProposalRepository`` y
los tests usan un repositorio en memoria.
"""

from __future__ import annotations

from typing import Protocol

from data.pipelines.rfp_intake.repository import TicketNotFoundError


class ProposalRepository(Protocol):
    def get_ticket(self, ticket_id: str) -> dict: ...

    def get_rfp_facts(self, ticket_id: str) -> dict: ...

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

    def complete_proposal(
        self,
        ticket_id: str,
        *,
        handoff: dict,
        status: str,
    ) -> None: ...

    def fail(self, ticket_id: str, *, stage: str, error: str) -> None: ...


__all__ = ["ProposalRepository", "TicketNotFoundError"]
