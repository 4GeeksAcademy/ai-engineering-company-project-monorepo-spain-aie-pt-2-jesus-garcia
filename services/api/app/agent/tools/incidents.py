"""Tool de consulta del gestor de incidencias (solo lectura, in-process).

Lee de la misma capa de servicio que ``GET /api/incidents`` y
``GET /api/incidents/{id}``. No hay dataset simulado ni escrituras: únicamente
se ejecutan lecturas sobre TinyDB.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from .contracts import (
    IncidentLookupInput,
    IncidentLookupOutput,
    IncidentRecord,
)
from .execution import ToolTimeout, call_with_timeout, incident_timeout_seconds

logger = logging.getLogger(__name__)

TOOL_NAME = "incident_lookup"


def _record_from_doc(doc: Any) -> IncidentRecord:
    # Import perezoso: mantiene el paquete importable en entornos que solo
    # ejecutan los evals con dobles (sin TinyDB instalado).
    from ...services import incident_service

    return IncidentRecord(
        id=str(doc.doc_id),
        title=doc.get("title", ""),
        description=doc.get("description"),
        description_excerpt=incident_service.description_excerpt(
            doc.get("description")
        ),
        origin=doc.get("origin", ""),
        branch=doc.get("branch", ""),
        category=doc.get("category", ""),
        status=doc.get("status", ""),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


def _read_incidents(payload: IncidentLookupInput) -> IncidentLookupOutput:
    from database import get_tinydb

    from ...services import incident_service

    db = get_tinydb()
    try:
        table = db.table("incidents")
        if payload.ticket_id is not None:
            doc = incident_service.find_incident(table, payload.ticket_id)
            if doc is None:
                return IncidentLookupOutput(
                    ok=False,
                    found=False,
                    error="not_found",
                    message=(
                        f"No existe la incidencia {payload.ticket_id} en el "
                        "gestor de incidencias."
                    ),
                )
            return IncidentLookupOutput(
                ok=True,
                found=True,
                incidents=[_record_from_doc(doc)],
            )

        docs = incident_service.list_incidents(
            table,
            status=payload.status,
            origin=payload.origin,
            branch=payload.branch,
            category=payload.category,
        )
        records = [_record_from_doc(doc) for doc in docs[: payload.limit]]
        if not records:
            return IncidentLookupOutput(
                ok=False,
                found=False,
                error="not_found",
                message=(
                    "No hay incidencias que coincidan con esos filtros en el "
                    "gestor de incidencias."
                ),
            )
        return IncidentLookupOutput(
            ok=True,
            found=True,
            incidents=records,
        )
    finally:
        db.close()


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if errors:
        message = str(errors[0].get("msg") or "Entrada inválida.")
        return message.removeprefix("Value error, ")
    return "Entrada inválida."


def lookup_incident(
    payload: IncidentLookupInput | dict,
    *,
    timeout_seconds: float | None = None,
) -> IncidentLookupOutput:
    """Consulta tickets en el gestor real, con timeout y fallback tipado."""
    if not isinstance(payload, IncidentLookupInput):
        try:
            payload = IncidentLookupInput.model_validate(payload)
        except ValidationError as exc:
            return IncidentLookupOutput(
                ok=False,
                found=False,
                error="invalid_input",
                message=_validation_message(exc),
            )

    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else incident_timeout_seconds()
    )

    try:
        return call_with_timeout(lambda: _read_incidents(payload), timeout)
    except ToolTimeout:
        logger.warning(
            "Timeout consultando incidencias tras %s segundos", timeout
        )
        return IncidentLookupOutput(
            ok=False,
            found=False,
            error="timeout",
            message="El gestor de incidencias no respondió a tiempo.",
        )
    except Exception:  # noqa: BLE001 - se devuelve un fallback controlado
        logger.exception("Fallo consultando el gestor de incidencias")
        return IncidentLookupOutput(
            ok=False,
            found=False,
            error="unavailable",
            message="No se pudo consultar el gestor de incidencias.",
        )


__all__ = ["TOOL_NAME", "lookup_incident"]
