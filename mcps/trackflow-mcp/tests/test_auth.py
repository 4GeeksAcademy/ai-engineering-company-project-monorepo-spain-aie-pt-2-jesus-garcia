"""Tests de autenticación, PRM y autorización por scope."""

from __future__ import annotations

import json

import pytest


def _sse(response) -> dict:
    for line in response.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    return json.loads(response.text)


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1"},
    },
}


async def _initialize(client, token: str | None) -> None:
    response = await client.post("/mcp", json=INITIALIZE, headers=_headers(token))
    assert response.status_code == 200, response.text


async def _call(client, token: str, name: str, arguments: dict):
    await _initialize(client, token)
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=_headers(token),
    )
    return response


def _error_payload(response) -> dict:
    payload = _sse(response)
    result = payload["result"]
    assert result["isError"] is True
    text = result["content"][0]["text"]
    raw = text.split(": ", 1)[1] if ": " in text else text
    return json.loads(raw)


async def test_protected_resource_metadata_is_public(client):
    response = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert response.status_code == 200
    payload = response.json()
    assert payload["resource"] == "https://mcp.test/mcp"
    assert payload["authorization_servers"] == ["https://issuer.test/"]
    assert payload["scopes_supported"] == ["mcp:read", "mcp:write"]
    assert payload["bearer_methods_supported"] == ["header"]


async def test_health_is_public(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize(
    "path",
    [
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
    ],
)
async def test_non_canonical_discovery_paths_return_404(client, path):
    response = await client.get(path)
    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"


async def test_mcp_without_token_returns_401(client):
    response = await client.post("/mcp", json=INITIALIZE, headers=_headers())
    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer")
    assert "resource_metadata=" in challenge
    assert "resource_metadata" in challenge
    payload = response.json()
    assert payload["error"] == "missing_auth_header"


async def test_invalid_token_returns_401(client):
    response = await client.post("/mcp", json=INITIALIZE, headers=_headers("bad"))
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"


async def test_missing_base_scope_returns_403(client):
    response = await client.post(
        "/mcp", json=INITIALIZE, headers=_headers("noscope")
    )
    assert response.status_code == 403
    assert "missing_required_scopes" in response.text


async def test_tools_list_requires_valid_token_and_exposes_schemas(client):
    await _initialize(client, "read")
    response = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers=_headers("read"),
    )
    assert response.status_code == 200
    tools = _sse(response)["result"]["tools"]
    by_name = {tool["name"]: tool for tool in tools}
    assert set(by_name) == {
        "query_incidents",
        "get_incident_summary",
        "create_incident",
        "update_incident_status",
        "query_inventory",
        "adjust_inventory_stock",
    }
    assert "mcp:read" in by_name["query_incidents"]["description"]
    assert "mcp:write" in by_name["create_incident"]["description"]
    assert "INVENTORY_READ_ONLY" in by_name["adjust_inventory_stock"]["description"]
    for tool in tools:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"
        assert tool.get("outputSchema")


async def test_write_tool_with_read_token_returns_insufficient_scope(client):
    response = await _call(
        client,
        "read",
        "create_incident",
        {
            "title": "Prueba",
            "description": "Prueba",
            "origin": "internal",
            "branch": "central",
            "category": "other",
        },
    )
    assert response.status_code == 200
    payload = _error_payload(response)
    assert payload["error_code"] == "INSUFFICIENT_SCOPE"
    assert payload["details"]["required_scope"] == "mcp:write"


async def test_inventory_write_guard_rejects_with_domain_code(client):
    response = await _call(
        client,
        "write",
        "adjust_inventory_stock",
        {"sku_id": 1, "quantity": 5, "operation": "inbound"},
    )
    assert response.status_code == 200
    payload = _error_payload(response)
    assert payload["error_code"] == "INVENTORY_READ_ONLY"
    assert payload["details"]["writable"] is False
