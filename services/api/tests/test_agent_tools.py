"""Tests del cliente MCP del agente (sin red ni servidor MCP real).

Se inyecta un invocador asíncrono que simula las tools MCP. Se comprueba que el
contrato tipado del agente se mantiene, que los errores del MCP se traducen a
fallbacks honestos y que el camino directo a TinyDB/SQLModel ya no existe.
"""

from __future__ import annotations

import asyncio
import importlib
import json

import httpx
import pytest

from app.agent.tools import (
    IncidentLookupInput,
    InventoryLookupInput,
    MCPAuthError,
    MCPSettings,
    MCPToolClient,
    MCPTokenProvider,
    lookup_incident,
    lookup_inventory,
    set_mcp_client_for_tests,
)
from app.agent.tools.mcp_client import MCPToolError


def incident_data(**overrides):
    data = {
        "id": "42",
        "title": "Paquete extraviado",
        "description": "El paquete no aparece en tránsito.",
        "description_excerpt": "El paquete no aparece en tránsito.",
        "origin": "customer",
        "branch": "la_warehouse",
        "category": "lost_parcel",
        "status": "in_progress",
        "created_at": "2026-11-01T10:00:00+00:00",
        "updated_at": "2026-11-02T10:00:00+00:00",
    }
    data.update(overrides)
    return data


def inventory_data(**overrides):
    data = {
        "id": 1,
        "name": "Classic White Sneaker - Size 42",
        "sku_code": "CLT-SNK-W-42",
        "warehouse": "los_angeles",
        "client_id": None,
        "min_stock": None,
        "current_stock": 47,
        "current_stock_by_warehouse": {"los_angeles": 47, "zaragoza": 0},
    }
    data.update(overrides)
    return data


def make_client(invokable, *, static_token: str = "test-token"):
    settings = MCPSettings(
        server_url="http://mcp.test/mcp",
        static_token=static_token,
        timeout_seconds=2,
    )
    return MCPToolClient(settings, invoker=invokable)


def test_lookup_incident_maps_structured_content():
    calls = []

    async def invoke(tool, arguments):
        calls.append((tool, arguments))
        return {"ok": True, "found": True, "incidents": [incident_data()]}

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_incident(IncidentLookupInput(ticket_id=42))
    finally:
        set_mcp_client_for_tests(None)

    assert result.ok is True
    assert result.found is True
    assert result.incidents[0].id == "42"
    assert calls == [("query_incidents", {"incident_id": "42", "limit": 20})]


def test_lookup_incident_maps_filters():
    calls = []

    async def invoke(tool, arguments):
        calls.append((tool, arguments))
        return {"ok": True, "found": True, "incidents": [incident_data()]}

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_incident(
            IncidentLookupInput(status="open", branch="la_warehouse")
        )
    finally:
        set_mcp_client_for_tests(None)

    assert result.found is True
    assert calls[0][1] == {
        "limit": 20,
        "status": "open",
        "branch": "la_warehouse",
    }


def test_lookup_incident_not_found_is_honest():
    async def invoke(tool, arguments):
        return {
            "ok": True,
            "found": False,
            "incidents": [],
            "message": "No hay incidencias.",
        }

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_incident(IncidentLookupInput(ticket_id=999))
    finally:
        set_mcp_client_for_tests(None)

    assert result.ok is False
    assert result.found is False
    assert result.error == "not_found"


def test_lookup_incident_maps_tool_error_codes():
    async def invoke(tool, arguments):
        raise RuntimeError(
            json.dumps(
                {
                    "error_code": "NOT_FOUND",
                    "message": "Incidencia 999 no encontrada.",
                }
            )
        )

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_incident(IncidentLookupInput(ticket_id=999))
    finally:
        set_mcp_client_for_tests(None)

    assert result.error == "not_found"
    assert "no encontrada" in result.message


def test_lookup_incident_scope_error_maps_to_forbidden():
    async def invoke(tool, arguments):
        raise MCPToolError("sin permisos", code="forbidden")

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_incident(IncidentLookupInput(ticket_id=1))
    finally:
        set_mcp_client_for_tests(None)

    assert result.error == "forbidden"


def test_lookup_incident_auth_error_maps_to_unavailable():
    async def invoke(tool, arguments):
        raise MCPAuthError("no token")

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_incident(IncidentLookupInput(ticket_id=1))
    finally:
        set_mcp_client_for_tests(None)

    assert result.error == "unavailable"


def test_lookup_incident_timeout_returns_timeout():
    async def invoke(tool, arguments):
        await asyncio.sleep(0.5)
        return {"ok": True, "found": True, "incidents": [incident_data()]}

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_incident(
            IncidentLookupInput(ticket_id=1), timeout_seconds=0.05
        )
    finally:
        set_mcp_client_for_tests(None)

    assert result.error == "timeout"
    assert "no respondió a tiempo" in result.message


def test_lookup_inventory_maps_items():
    calls = []

    async def invoke(tool, arguments):
        calls.append((tool, arguments))
        return {"ok": True, "found": True, "items": [inventory_data()]}

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_inventory(
            InventoryLookupInput(sku_code="CLT-SNK-W-42")
        )
    finally:
        set_mcp_client_for_tests(None)

    assert result.ok is True
    assert result.items[0].current_stock == 47
    assert result.items[0].current_stock_by_warehouse["los_angeles"] == 47
    assert calls == [
        (
            "query_inventory",
            {"sku_code": "CLT-SNK-W-42", "limit": 20},
        )
    ]


def test_lookup_inventory_not_found_is_honest():
    async def invoke(tool, arguments):
        return {
            "ok": True,
            "found": False,
            "items": [],
            "message": "No hay productos.",
        }

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_inventory(InventoryLookupInput(sku_code="NOPE"))
    finally:
        set_mcp_client_for_tests(None)

    assert result.ok is False
    assert result.error == "not_found"


def test_invalid_input_is_rejected_before_mcp():
    calls = []

    async def invoke(tool, arguments):
        calls.append((tool, arguments))
        return {"ok": True, "found": True, "incidents": []}

    client = make_client(invoke)
    set_mcp_client_for_tests(client)
    try:
        result = lookup_incident({})
        inventory = lookup_inventory({})
    finally:
        set_mcp_client_for_tests(None)

    assert result.error == "invalid_input"
    assert inventory.error == "invalid_input"
    assert calls == []


def test_direct_tool_modules_are_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.agent.tools.incidents")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.agent.tools.inventory")


def test_token_provider_uses_client_credentials_and_caches():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"access_token": "mcp-token", "expires_in": 3600},
        )

    settings = MCPSettings(
        server_url="http://mcp.test/mcp",
        token_url="https://issuer.test/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
        audience="https://mcp.test/mcp",
        scopes=["mcp:read"],
    )
    provider = MCPTokenProvider(
        settings, transport=httpx.MockTransport(handler)
    )

    async def run():
        first = await provider.get_token()
        second = await provider.get_token()
        return first, second

    assert asyncio.run(run()) == ("mcp-token", "mcp-token")
    assert len(seen) == 1
    body = seen[0].content.decode()
    assert "grant_type=client_credentials" in body
    assert "audience=https%3A%2F%2Fmcp.test%2Fmcp" in body
    assert "scope=mcp%3Aread" in body


def test_token_provider_failure_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid_client")

    settings = MCPSettings(
        server_url="http://mcp.test/mcp",
        token_url="https://issuer.test/oauth/token",
        client_id="client-id",
        client_secret="bad",
    )
    provider = MCPTokenProvider(
        settings, transport=httpx.MockTransport(handler)
    )

    async def run():
        with pytest.raises(MCPAuthError):
            await provider.get_token()

    asyncio.run(run())
