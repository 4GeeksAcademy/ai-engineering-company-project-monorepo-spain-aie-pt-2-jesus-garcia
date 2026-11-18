"""Tools de incidencias contra el Incidents Manager real.

Todas las operaciones llaman a la API REST existente
(``services/api/app/routes/incidents_manager.py``). Crear y consultar usan sus
endpoints; cualquier cambio de estado pasa **exclusivamente** por
``PATCH /api/incidents/{id}/status`` para respetar la máquina de estados.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..backend import get_api
from ..models import (
    IncidentBranch,
    IncidentCategory,
    IncidentMutationOutput,
    IncidentOrigin,
    IncidentQueryOutput,
    IncidentRecord,
    IncidentStatus,
    IncidentSummaryOutput,
)
from .guards import tool_guard

READ_SCOPE = "mcp:read"
WRITE_SCOPE = "mcp:write"


@tool_guard("query_incidents", READ_SCOPE)
async def query_incidents(
    incident_id: Annotated[
        str | None,
        Field(
            description=(
                "ID de la incidencia (campo `id` de GET /api/incidents). "
                "Si se indica, se devuelve esa incidencia y se ignoran los filtros."
            )
        ),
    ] = None,
    status: Annotated[
        IncidentStatus | None,
        Field(description="Estado: open, in_progress, resolved o discarded."),
    ] = None,
    origin: Annotated[
        IncidentOrigin | None,
        Field(description="Origen: customer, branch o internal."),
    ] = None,
    branch: Annotated[
        IncidentBranch | None,
        Field(
            description=(
                "Sede: central, la_warehouse, la_office, zaragoza_warehouse "
                "o zaragoza_office."
            )
        ),
    ] = None,
    category: Annotated[
        IncidentCategory | None,
        Field(description="Categoría de la incidencia."),
    ] = None,
    limit: Annotated[
        int,
        Field(
            ge=1,
            le=50,
            description="Máximo de incidencias a devolver (1-50).",
        ),
    ] = 20,
) -> IncidentQueryOutput:
    """Consulta incidencias en tiempo real del gestor de incidentes.

    Úsala para preguntas como "¿en qué estado está el ticket 482?", "incidencias
    abiertas de la sede de Zaragoza" o "incidencias de paquete perdido". Los
    datos son operativos y cambian en vivo: nunca se responden desde el RAG.

    Requiere el scope `mcp:read`. Devuelve `ok=true, found=false` si la búsqueda
    no tiene resultados; una incidencia inexistente por ID devuelve el error
    `NOT_FOUND`.
    """
    api = get_api()

    if incident_id is not None:
        payload = await api.get(f"/api/incidents/{quote(str(incident_id), safe='')}")
        record = IncidentRecord.model_validate(payload)
        return IncidentQueryOutput(ok=True, found=True, incidents=[record])

    payload = await api.get(
        "/api/incidents",
        params={
            "status": status,
            "origin": origin,
            "branch": branch,
            "category": category,
        },
    )
    records = [IncidentRecord.model_validate(item) for item in payload]
    records = records[:limit]
    return IncidentQueryOutput(
        ok=True,
        found=bool(records),
        incidents=records,
        message="" if records else "No hay incidencias que coincidan con los filtros.",
    )


@tool_guard("get_incident_summary", READ_SCOPE)
async def get_incident_summary() -> IncidentSummaryOutput:
    """Devuelve métricas agregadas del gestor de incidentes en tiempo real.

    Incluye conteos por estado, categoría, origen y sede. Útil para preguntas
    como "¿cuántas incidencias hay abiertas?" o "resumen de incidencias por
    sede". Requiere el scope `mcp:read`.
    """
    payload = await get_api().get("/api/incidents/summary")
    return IncidentSummaryOutput(
        ok=True,
        by_status=payload.get("by_status", {}),
        by_category=payload.get("by_category", {}),
        by_origin=payload.get("by_origin", {}),
        by_branch=payload.get("by_branch", {}),
    )


@tool_guard("create_incident", WRITE_SCOPE)
async def create_incident(
    title: Annotated[
        str,
        Field(min_length=1, max_length=200, description="Título breve de la incidencia."),
    ],
    description: Annotated[
        str,
        Field(min_length=1, max_length=4000, description="Descripción detallada."),
    ],
    origin: Annotated[
        IncidentOrigin,
        Field(description="Origen: customer, branch o internal."),
    ],
    branch: Annotated[
        IncidentBranch,
        Field(
            description=(
                "Sede: central, la_warehouse, la_office, zaragoza_warehouse "
                "o zaragoza_office."
            )
        ),
    ],
    category: Annotated[
        IncidentCategory,
        Field(description="Categoría de la incidencia."),
    ],
) -> IncidentMutationOutput:
    """Crea una incidencia en el gestor real.

    La incidencia nace siempre en estado `open`; los cambios posteriores deben
    hacerse con `update_incident_status` para respetar las transiciones.
    Requiere el scope `mcp:write`.
    """
    payload = await get_api().post(
        "/api/incidents",
        json={
            "title": title.strip(),
            "description": description.strip(),
            "origin": origin,
            "branch": branch,
            "category": category,
            "status": "open",
        },
    )
    return IncidentMutationOutput(
        ok=True, incident=IncidentRecord.model_validate(payload)
    )


@tool_guard("update_incident_status", WRITE_SCOPE)
async def update_incident_status(
    incident_id: Annotated[
        str, Field(min_length=1, description="ID de la incidencia a actualizar.")
    ],
    status: Annotated[
        IncidentStatus,
        Field(description="Nuevo estado: open, in_progress, resolved o discarded."),
    ],
) -> IncidentMutationOutput:
    """Cambia el estado de una incidencia usando el endpoint de ciclo de vida.

    Llama a `PATCH /api/incidents/{id}/status`, que valida la transición:
    `open → in_progress|discarded`, `in_progress → resolved|discarded|open`,
    `resolved → in_progress`, `discarded` es final. Una transición ilegal
    devuelve `INVALID_STATUS_TRANSITION` con el detalle de las permitidas.
    Requiere el scope `mcp:write`.
    """
    payload = await get_api().patch(
        f"/api/incidents/{quote(str(incident_id), safe='')}/status",
        json={"status": status},
    )
    return IncidentMutationOutput(
        ok=True, incident=IncidentRecord.model_validate(payload)
    )


def register_incident_tools(mcp: FastMCP) -> None:
    mcp.tool(
        name="query_incidents",
        description=(
            "Consulta en tiempo real el gestor de incidencias de TrackFlow. "
            "Busca por ID o por filtros (estado, origen, sede, categoría). "
            "Requiere scope mcp:read."
        ),
    )(query_incidents)
    mcp.tool(
        name="get_incident_summary",
        description=(
            "Devuelve métricas agregadas del gestor de incidencias (por estado, "
            "categoría, origen y sede). Requiere scope mcp:read."
        ),
    )(get_incident_summary)
    mcp.tool(
        name="create_incident",
        description=(
            "Crea una incidencia real en estado open. Los cambios de estado se "
            "hacen con update_incident_status. Requiere scope mcp:write."
        ),
    )(create_incident)
    mcp.tool(
        name="update_incident_status",
        description=(
            "Cambia el estado de una incidencia mediante el endpoint de ciclo "
            "de vida PATCH /api/incidents/{id}/status, validando la transición. "
            "Requiere scope mcp:write."
        ),
    )(update_incident_status)


__all__ = [
    "create_incident",
    "get_incident_summary",
    "query_incidents",
    "register_incident_tools",
    "update_incident_status",
]
