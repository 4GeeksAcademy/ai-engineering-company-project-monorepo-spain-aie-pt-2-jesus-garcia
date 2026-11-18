"""Capa de servicio de solo lectura del gestor de incidencias.

Las rutas REST y la tool del agente comparten estas funciones: no existe un
dataset paralelo ni se duplica la lógica de filtrado. Todas las operaciones son
de lectura; crear/actualizar/eliminar sigue viviendo en las rutas de escritura.
"""

from __future__ import annotations

from typing import Any

from models import Incident, IncidentListItem


def find_incident(table, incident_id: str | int):
    """Devuelve el documento de TinyDB o ``None`` si no existe."""
    raw = str(incident_id)
    target_id = int(raw) if raw.isdigit() else raw
    for doc in table.all():
        if doc.doc_id == target_id:
            return doc
    return None


def list_incidents(
    table,
    *,
    status: str | None = None,
    origin: str | None = None,
    branch: str | None = None,
    category: str | None = None,
) -> list:
    """Lista documentos aplicando los mismos filtros que ``GET /api/incidents``."""
    results = []
    for doc in table.all():
        if status and doc.get("status") != status:
            continue
        if origin and doc.get("origin") != origin:
            continue
        if branch and doc.get("branch") != branch:
            continue
        if category and doc.get("category") != category:
            continue
        results.append(doc)
    return results


def description_excerpt(description: Any, limit: int = 120) -> str:
    text = str(description or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def to_incident(doc) -> Incident:
    """Mapea un documento TinyDB al contrato completo de la API."""
    return Incident(id=str(doc.doc_id), **dict(doc))


def to_list_item(doc) -> IncidentListItem:
    """Mapea un documento TinyDB al contrato slim de listado."""
    return IncidentListItem(
        id=str(doc.doc_id),
        title=doc.get("title", ""),
        description_excerpt=description_excerpt(doc.get("description", "")),
        origin=doc.get("origin", ""),
        branch=doc.get("branch", ""),
        category=doc.get("category", ""),
        status=doc.get("status", ""),
    )


__all__ = [
    "description_excerpt",
    "find_incident",
    "list_incidents",
    "to_incident",
    "to_list_item",
]
