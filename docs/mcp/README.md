# MCP — Servidor de operaciones y migración del agente

Documentación de la entrega del **MCP Server** protegido con OAuth 2.1 y de la
migración del agente LangGraph para consumirlo con `langchain-mcp-adapters`.

## Piezas

| Pieza | Ruta |
|---|---|
| Servidor MCP | [`mcps/trackflow-mcp/`](../../mcps/trackflow-mcp/README.md) |
| Validación y evidencias | [`mcps/trackflow-mcp/VALIDATION.md`](../../mcps/trackflow-mcp/VALIDATION.md) |
| Cliente MCP del agente | `services/api/app/agent/tools/mcp_client.py` |
| Token OAuth del agente | `services/api/app/agent/tools/mcp_auth.py` |
| Tools del servidor | `mcps/trackflow-mcp/trackflow_mcp/tools/` |

## Flujo de autorización

```text
MCPJam / cliente
   │ 1. POST /mcp sin token
   ▼
MCP Server ──► 401 + WWW-Authenticate con resource_metadata
   │
   │ 2. GET /.well-known/oauth-protected-resource/mcp
   ▼
PRM: resource + authorization_servers (Auth0) + scopes
   │
   │ 3. OAuth 2.1 + PKCE / DCR contra Auth0
   ▼
Access token JWT (aud = .../mcp, scopes mcp:read|mcp:write)
   │
   │ 4. POST /mcp con Authorization: Bearer
   ▼
mcpauth valida firma, iss, aud, exp y mcp:read
   │
   ▼
Tool → API real (Incidents Manager / inventario)
```

## Tools

| Tool | Scope | Efecto |
|---|---|---|
| `query_incidents` | `mcp:read` | Lee tickets en tiempo real. |
| `get_incident_summary` | `mcp:read` | Agregados por estado/categoría/origen/sede. |
| `create_incident` | `mcp:write` | Crea ticket en `open`. |
| `update_incident_status` | `mcp:write` | `PATCH /api/incidents/{id}/status`. |
| `query_inventory` | `mcp:read` | Stock por SKU/almacén. |
| `adjust_inventory_stock` | `mcp:write` | **Siempre** rechaza con `INVENTORY_READ_ONLY`. |

## Migración del agente

- `app/agent/tools/incidents.py` y `inventory.py` fueron eliminados.
- `app/agent/nodes.py` mantiene las rutas y el estado; solo cambia la
  implementación de las tools.
- `mcp_client.py` traduce cualquier error del MCP a `IncidentLookupOutput` /
  `InventoryLookupOutput` con `error` tipado (`not_found`, `forbidden`,
  `timeout`, `unavailable`, `invalid_input`).
- El endpoint `/agent/query` sigue devolviendo `200` con fallback cuando la tool
  falla; solo los fallos internos del grafo dan `502`.
- Los evals `tests/pipelines/test_agent_evals.py` siguen pasando (23) y se
  añadieron tests de fallback MCP en `services/api/tests/test_agent_mcp_failures.py`.

## Validación con MCPJam (pendiente de credenciales M2M)

1. Arrancar API y MCP en el Codespace.
2. `gh codespace ports visibility 8001:public`.
3. Verificar el PRM público.
4. Añadir `https://<codespace>-8001.app.github.dev/mcp` en MCPJam y completar
   el consentimiento OAuth de Auth0.
5. Ejecutar las 6 tools y capturar la evidencia en `docs/mcp/playground/`.
6. Ejecutar `scripts/mcp_smoke.py` con el token M2M para la comprobación
   determinista.

Consulta el detalle y los comandos exactos en
[`VALIDATION.md`](../../mcps/trackflow-mcp/VALIDATION.md).
