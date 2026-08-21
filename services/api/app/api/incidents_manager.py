from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_db
from models import (
    FINAL_INCIDENT_STATUSES,
    INCIDENT_BRANCHES,
    INCIDENT_CATEGORIES,
    INCIDENT_ORIGINS,
    INCIDENT_STATUS_TRANSITIONS,
    INCIDENT_STATUSES,
    Incident,
    IncidentCreate,
    IncidentStatusUpdate,
    IncidentSummary,
)
from app.core.dependencies import require_manager

router = APIRouter(prefix="/incidents", tags=["incident-manager"])


def _find_incident(table, incident_id):
    target_id = int(incident_id) if incident_id.isdigit() else incident_id
    for doc in table.all():
        if doc.doc_id == target_id:
            return doc
    return None


def _validate_create(data: dict) -> None:
    required = ["title", "description", "origin", "branch", "category"]
    missing = [f for f in required if not str(data.get(f, "")).strip()]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Campos obligatorios faltantes o vacíos: {', '.join(missing)}.",
        )
    if data["origin"] not in INCIDENT_ORIGINS:
        raise HTTPException(
            status_code=400,
            detail=f"origin inválido. Debe ser uno de: {', '.join(INCIDENT_ORIGINS)}.",
        )
    if data["branch"] not in INCIDENT_BRANCHES:
        raise HTTPException(
            status_code=400,
            detail=f"branch inválido. Debe ser uno de: {', '.join(INCIDENT_BRANCHES)}.",
        )
    if data["category"] not in INCIDENT_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"category inválido. Debe ser uno de: {', '.join(INCIDENT_CATEGORIES)}.",
        )
    if data["status"] not in INCIDENT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status inválido. Debe ser uno de: {', '.join(INCIDENT_STATUSES)}.",
        )


@router.get(
    "/summary",
    response_model=IncidentSummary,
    summary="Métricas agregadas de incidencias",
)
def incident_summary(_=Depends(require_manager)) -> IncidentSummary:
    db = get_db()
    table = db.table("incidents")

    summary = {
        "by_status": {status: 0 for status in INCIDENT_STATUSES},
        "by_category": {category: 0 for category in INCIDENT_CATEGORIES},
        "by_origin": {origin: 0 for origin in INCIDENT_ORIGINS},
        "by_branch": {branch: 0 for branch in INCIDENT_BRANCHES},
    }

    for doc in table.all():
        summary["by_status"][doc.get("status", "")] = summary["by_status"].get(doc["status"], 0) + 1
        summary["by_category"][doc.get("category", "")] = summary["by_category"].get(doc["category"], 0) + 1
        summary["by_origin"][doc.get("origin", "")] = summary["by_origin"].get(doc["origin"], 0) + 1
        summary["by_branch"][doc.get("branch", "")] = summary["by_branch"].get(doc["branch"], 0) + 1

    db.close()
    return IncidentSummary(**summary)


@router.get(
    "",
    response_model=list[Incident],
    summary="Listar incidencias con filtros opcionales",
)
def list_incidents(
    status: str | None = Query(None, description="Filtrar por estado"),
    origin: str | None = Query(None, description="Filtrar por origen"),
    branch: str | None = Query(None, description="Filtrar por sede"),
    category: str | None = Query(None, description="Filtrar por categoría"),
    _=Depends(require_manager),
) -> list[Incident]:
    db = get_db()
    table = db.table("incidents")

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
        results.append(Incident(id=str(doc.doc_id), **doc))

    db.close()
    return results


@router.get(
    "/{incident_id}",
    response_model=Incident,
    summary="Obtener una incidencia por ID",
)
def get_incident(incident_id: str, _=Depends(require_manager)) -> Incident:
    db = get_db()
    table = db.table("incidents")

    doc = _find_incident(table, incident_id)
    if doc is None:
        db.close()
        raise HTTPException(status_code=404, detail=f"Incidencia {incident_id} no encontrada.")

    db.close()
    return Incident(id=str(doc.doc_id), **doc)


@router.post(
    "",
    response_model=Incident,
    status_code=201,
    summary="Crear una nueva incidencia",
)
def create_incident(payload: IncidentCreate, _=Depends(require_manager)) -> Incident:
    _validate_create(payload.model_dump())

    db = get_db()
    table = db.table("incidents")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "title": payload.title,
        "description": payload.description,
        "origin": payload.origin,
        "branch": payload.branch,
        "category": payload.category,
        "status": payload.status,
        "created_at": now,
        "updated_at": now,
    }

    doc_id = table.insert(doc)
    db.close()
    return Incident(id=str(doc_id), **doc)


@router.patch(
    "/{incident_id}/status",
    response_model=Incident,
    summary="Cambiar el estado de una incidencia validando la transición",
)
def update_incident_status(
    incident_id: str, payload: IncidentStatusUpdate, _=Depends(require_manager)
) -> Incident:
    new_status = payload.status
    if new_status not in INCIDENT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status inválido. Debe ser uno de: {', '.join(INCIDENT_STATUSES)}.",
        )

    db = get_db()
    table = db.table("incidents")

    doc = _find_incident(table, incident_id)
    if doc is None:
        db.close()
        raise HTTPException(status_code=404, detail=f"Incidencia {incident_id} no encontrada.")

    current = doc["status"]
    if new_status != current:
        allowed = INCIDENT_STATUS_TRANSITIONS[current]
        if new_status not in allowed:
            db.close()
            if current in FINAL_INCIDENT_STATUSES:
                detail = f"La incidencia está en estado final '{current}' y no admite cambios."
            else:
                allowed_text = ", ".join(sorted(allowed)) if allowed else "ninguno"
                detail = (
                    f"Transición inválida de '{current}' a '{new_status}'. "
                    f"Transiciones permitidas desde '{current}': {allowed_text}."
                )
            raise HTTPException(status_code=400, detail=detail)

        update_data = {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        table.update(update_data, doc_ids=[doc.doc_id])

    for d in table.all():
        if d.doc_id == doc.doc_id:
            db.close()
            return Incident(id=str(doc.doc_id), **d)

    db.close()
    raise HTTPException(status_code=404, detail=f"Incidencia {incident_id} no encontrada.")
