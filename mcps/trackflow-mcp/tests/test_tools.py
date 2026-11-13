"""Tests de las tools contra un doble de la API real."""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from trackflow_mcp.errors import BackendError, ErrorCode
from trackflow_mcp.tools.incidents import (
    create_incident,
    get_incident_summary,
    query_incidents,
    update_incident_status,
)
from trackflow_mcp.tools.inventory import (
    adjust_inventory_stock,
    query_inventory,
)

INCIDENT = {
    "id": "42",
    "title": "Paquete extraviado",
    "description": "El paquete no aparece en tránsito.",
    "origin": "customer",
    "branch": "la_warehouse",
    "category": "lost_parcel",
    "status": "open",
    "created_at": "2026-11-01T10:00:00+00:00",
    "updated_at": "2026-11-01T10:00:00+00:00",
}

LIST_ITEM = {
    "id": "42",
    "title": "Paquete extraviado",
    "description_excerpt": "El paquete no aparece en tránsito.",
    "origin": "customer",
    "branch": "la_warehouse",
    "category": "lost_parcel",
    "status": "open",
}

INVENTORY = [
    {
        "id": 1,
        "name": "Classic White Sneaker - Size 42",
        "sku_code": "CLT-SNK-W-42",
        "warehouse": "los_angeles",
        "client_id": "client-a",
        "min_stock": 10,
        "current_stock": 47,
        "current_stock_by_warehouse": {"los_angeles": 47, "zaragoza": 0},
    },
    {
        "id": 2,
        "name": "Classic White Sneaker - Size 43",
        "sku_code": "CLT-SNK-W-43",
        "warehouse": "zaragoza",
        "client_id": "client-b",
        "min_stock": None,
        "current_stock": 5,
        "current_stock_by_warehouse": {"los_angeles": 0, "zaragoza": 5},
    },
]


def error_code(exc: ToolError) -> str:
    return json.loads(str(exc))["error_code"]


async def test_query_incident_by_id(read_auth, fake_api):
    fake_api.on("GET", "/api/incidents/42", INCIDENT)
    result = await query_incidents(incident_id="42")
    assert result.ok is True
    assert result.found is True
    assert result.incidents[0].id == "42"
    assert result.incidents[0].status == "open"


async def test_query_incidents_passes_filters_and_limit(read_auth, fake_api):
    fake_api.on("GET", "/api/incidents", [LIST_ITEM, LIST_ITEM])
    result = await query_incidents(
        status="open", branch="la_warehouse", limit=1
    )
    assert result.found is True
    assert len(result.incidents) == 1
    call = fake_api.calls[0]
    assert call["params"] == {
        "status": "open",
        "origin": None,
        "branch": "la_warehouse",
        "category": None,
    }


async def test_query_incidents_empty_is_not_an_error(read_auth, fake_api):
    fake_api.on("GET", "/api/incidents", [])
    result = await query_incidents(status="resolved")
    assert result.ok is True
    assert result.found is False
    assert result.incidents == []
    assert "No hay incidencias" in result.message


async def test_query_incident_not_found_is_mapped(read_auth, fake_api):
    fake_api.on(
        "GET",
        "/api/incidents/999",
        BackendError(
            ErrorCode.NOT_FOUND,
            "Incidencia 999 no encontrada.",
            status_code=404,
            path="/api/incidents/999",
        ),
    )
    with pytest.raises(ToolError) as exc:
        await query_incidents(incident_id="999")
    assert error_code(exc.value) == "NOT_FOUND"


async def test_incident_summary(read_auth, fake_api):
    fake_api.on(
        "GET",
        "/api/incidents/summary",
        {
            "by_status": {"open": 2},
            "by_category": {"lost_parcel": 2},
            "by_origin": {"customer": 2},
            "by_branch": {"la_warehouse": 2},
        },
    )
    result = await get_incident_summary()
    assert result.by_status == {"open": 2}
    assert result.by_branch == {"la_warehouse": 2}


async def test_create_incident_uses_real_endpoint_and_opens_ticket(
    write_auth, fake_api
):
    fake_api.on("POST", "/api/incidents", INCIDENT)
    result = await create_incident(
        title="Paquete extraviado",
        description="El paquete no aparece en tránsito.",
        origin="customer",
        branch="la_warehouse",
        category="lost_parcel",
    )
    assert result.ok is True
    assert result.incident.id == "42"
    call = fake_api.calls[0]
    assert call["json"]["status"] == "open"
    assert call["json"]["title"] == "Paquete extraviado"


async def test_update_status_uses_lifecycle_endpoint(write_auth, fake_api):
    updated = {**INCIDENT, "status": "in_progress"}
    fake_api.on("PATCH", "/api/incidents/42/status", updated)
    result = await update_incident_status(
        incident_id="42", status="in_progress"
    )
    assert result.incident.status == "in_progress"
    call = fake_api.calls[0]
    assert call["method"] == "PATCH"
    assert call["path"] == "/api/incidents/42/status"
    assert call["json"] == {"status": "in_progress"}


async def test_invalid_transition_is_mapped(write_auth, fake_api):
    fake_api.on(
        "PATCH",
        "/api/incidents/42/status",
        BackendError(
            ErrorCode.INVALID_STATUS_TRANSITION,
            "Transición inválida de 'open' a 'resolved'.",
            status_code=400,
            path="/api/incidents/42/status",
        ),
    )
    with pytest.raises(ToolError) as exc:
        await update_incident_status(incident_id="42", status="resolved")
    assert error_code(exc.value) == "INVALID_STATUS_TRANSITION"


async def test_query_inventory_by_sku_code(read_auth, fake_api):
    fake_api.on("GET", "/inventory/products", INVENTORY)
    result = await query_inventory(sku_code="clt-snk-w-42")
    assert result.found is True
    assert len(result.items) == 1
    assert result.items[0].current_stock == 47
    assert result.items[0].current_stock_by_warehouse["los_angeles"] == 47


async def test_query_inventory_by_warehouse(read_auth, fake_api):
    fake_api.on("GET", "/inventory/products", INVENTORY)
    result = await query_inventory(warehouse="zaragoza")
    assert result.found is True
    assert [item.sku_code for item in result.items] == ["CLT-SNK-W-43"]


async def test_query_inventory_by_name(read_auth, fake_api):
    fake_api.on("GET", "/inventory/products", INVENTORY)
    result = await query_inventory(name_query="size 42")
    assert result.found is True
    assert result.items[0].sku_code == "CLT-SNK-W-42"


async def test_query_inventory_empty_is_not_an_error(read_auth, fake_api):
    fake_api.on("GET", "/inventory/products", INVENTORY)
    result = await query_inventory(sku_code="DOES-NOT-EXIST")
    assert result.ok is True
    assert result.found is False
    assert "No hay productos" in result.message


async def test_inventory_write_guard_never_calls_api(write_auth, fake_api):
    with pytest.raises(ToolError) as exc:
        await adjust_inventory_stock(
            sku_id=1, quantity=5, operation="inbound"
        )
    assert error_code(exc.value) == "INVENTORY_READ_ONLY"
    assert fake_api.calls == []
