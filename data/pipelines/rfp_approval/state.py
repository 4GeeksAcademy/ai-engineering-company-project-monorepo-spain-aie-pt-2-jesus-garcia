"""Estado de los grafos de la Parte 3."""

from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict


def merge_sections(
    left: dict[str, dict] | None,
    right: dict[str, dict] | None,
) -> dict[str, dict]:
    """Reducer para que cada rama de aprobación actualice solo su sección."""

    merged = dict(left or {})
    merged.update(right or {})
    return merged


def merge_dict(
    left: dict | None,
    right: dict | None,
) -> dict:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class ApprovalState(TypedDict, total=False):
    ticket_id: str
    thread_id: str
    rfp_id: str | None
    proposal: dict
    intake: dict
    client: dict
    client_country: str | None
    currency: str | None
    sections: Annotated[dict[str, dict], merge_sections]
    briefs: dict[str, dict]
    conflicts: list[dict]
    arbitration_results: list[dict]
    arbitration_round: int
    max_rounds: int
    status: str
    final_document: dict | None
    gate: dict
    error: str | None
    events: Annotated[list[dict], add]


class BranchState(TypedDict, total=False):
    ticket_id: str
    thread_id: str
    department_id: str
    section: dict
    context: dict
    packet: dict
    decision: dict
    approval_round: int
    max_rounds: int
    status: str
    events: Annotated[list[dict], add]
