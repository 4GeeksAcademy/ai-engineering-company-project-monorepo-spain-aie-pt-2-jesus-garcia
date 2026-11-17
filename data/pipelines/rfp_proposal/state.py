"""Estado de los grafos de la Parte 2."""

from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict


def merge_sections(
    left: dict[str, dict] | None,
    right: dict[str, dict] | None,
) -> dict[str, dict]:
    """Reducer para que cada departamento paralelo añada su sección."""

    merged = dict(left or {})
    merged.update(right or {})
    return merged


def merge_evaluations(
    left: dict[str, dict] | None,
    right: dict[str, dict] | None,
) -> dict[str, dict]:
    """Reducer para que los evaluadores paralelos no colisionen.

    Cada evaluador escribe solo su clave (``readability`` / ``relevance`` /
    ``compliance``); nadie sobrescribe el resultado de otro.
    """

    merged = dict(left or {})
    merged.update(right or {})
    return merged


class SectionState(TypedDict, total=False):
    ticket_id: str
    brief: dict
    draft: dict
    evaluations: Annotated[dict[str, dict], merge_evaluations]
    result: dict
    iteration: int
    max_iterations: int
    events: Annotated[list[dict], add]


class ProposalState(TypedDict, total=False):
    ticket_id: str
    handoff: dict
    briefs: list[dict]
    brief: dict
    max_iterations: int
    sections: Annotated[dict[str, dict], merge_sections]
    proposal_handoff: dict
    status: str
    error: str | None
    events: Annotated[list[dict], add]
