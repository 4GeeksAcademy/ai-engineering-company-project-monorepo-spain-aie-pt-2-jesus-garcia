"""Puerto de persistencia del pipeline ``rfp_intake``.

El pipeline no importa SQLModel ni conoce PostgreSQL: recibe una implementación
de este Protocol. La API/worker inyecta ``SqlRfpRepository``; los tests usan un
repositorio en memoria.
"""

from __future__ import annotations

from typing import Protocol, TypedDict


class TicketNotFoundError(LookupError):
    """El ticket no existe o fue borrado entre la subida y el procesamiento."""


class TicketSnapshot(TypedDict):
    ticket_id: str
    rfp_id: str
    status: str
    raw_pdf_path: str
    markdown_path: str | None
    pipeline_stage: str | None


class RfpRepository(Protocol):
    def get_ticket(self, ticket_id: str) -> dict: ...

    def mark_processing(self, ticket_id: str) -> None: ...

    def set_stage(self, ticket_id: str, stage: str) -> None: ...

    def save_conversion(
        self,
        ticket_id: str,
        *,
        markdown_path: str,
        document_metadata: dict,
        readability: dict,
    ) -> None: ...

    def save_metadata(
        self,
        ticket_id: str,
        *,
        metadata: dict,
        classification: dict,
    ) -> None: ...

    def save_plan(self, ticket_id: str, *, departments: list[str]) -> None: ...

    def save_section(self, ticket_id: str, *, section: dict) -> None: ...

    def discard(
        self,
        ticket_id: str,
        *,
        reason: str,
        classification: dict,
        stage: str = "descartado",
    ) -> None: ...

    def complete(
        self,
        ticket_id: str,
        *,
        handoff: dict,
        stage: str = "completado",
    ) -> None: ...

    def fail(
        self,
        ticket_id: str,
        *,
        stage: str,
        error: str,
    ) -> None: ...
