"""Estado compartido por los nodos del grafo ``rfp_intake``."""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict

RfpStatus = Literal["processing", "discarded", "completed", "error"]


def merge_sections(
    left: dict[str, dict] | None,
    right: dict[str, dict] | None,
) -> dict[str, dict]:
    """Reducer que permite a los workers paralelos añadir su propia sección."""

    merged = dict(left or {})
    merged.update(right or {})
    return merged


class RfpIntakeState(TypedDict, total=False):
    """Todo lo que necesita el grafo para convertir una RFP en un handoff.

    El Markdown completo vive en el estado solo durante la ejecución; ni el
    handoff ni la traza lo persisten (el artefacto queda en ``data/raw``).
    """

    ticket_id: str
    rfp_id: str
    pdf_path: str
    markdown_path: str

    markdown: str
    document_metadata: dict
    readability: dict

    classification: dict
    is_rfp: bool
    discard_reason: str | None

    metadata: dict
    unknown_services: list[str]

    plan: list[dict]
    workstream: dict
    sections: Annotated[dict[str, dict], merge_sections]
    conflicts: list[dict]

    sales_summary: str
    handoff: dict

    status: RfpStatus
    stage: str
    error: str | None
    events: Annotated[list[dict], add]
