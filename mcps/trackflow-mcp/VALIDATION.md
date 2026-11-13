# Validación del MCP Server

Fecha: 2026-11-13
Rama: `feature/mcp-oauth-tools`
Entorno: macOS local + Codespaces (URL pública de validación).

## Configuración usada

| Parámetro | Valor |
|---|---|
| `MCP_RESOURCE_URL` | `https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/mcp` |
| `MCP_AUTH_ISSUER` | `https://dev-hfpsbxjc0cragdyx.us.auth0.com/` |
| Scopes | `mcp:read`, `mcp:write` |
| API real | `http://localhost:8002` (SQLite local para la demo) |
| Cuenta de servicio | `mcp-service@trackflow.com` (rol `manager`) |

## 1. Discovery y PRM

```bash
curl -s https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/.well-known/oauth-protected-resource/mcp
```

Resultado local equivalente (`http://127.0.0.1:8001`):

```json
{
  "resource": "https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/mcp",
  "scopes_supported": ["mcp:read", "mcp:write"],
  "bearer_methods_supported": ["header"],
  "resource_name": "TrackFlow Operations MCP",
  "authorization_servers": ["https://dev-hfpsbxjc0cragdyx.us.auth0.com/"]
}
```

- [x] `GET /.well-known/oauth-protected-resource/mcp` → **200**.
- [x] `GET /health` → **200** (público, sin datos de la compañía).

## 2. Sin token no se puede listar ni invocar

```bash
curl -i -X POST http://127.0.0.1:8001/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

Resultado:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="missing_auth_header", error_description="Missing `Authorization` header. Please provide a valid bearer token.", resource_metadata="https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/.well-known/oauth-protected-resource/mcp"

{"error":"missing_auth_header","error_description":"Missing `Authorization` header. Please provide a valid bearer token."}
```

Token malformado:

```http
HTTP/1.1 401 Unauthorized
{"error":"invalid_token","error_description":"The provided token is invalid or malformed."}
```

- [x] Sin token → 401 + `WWW-Authenticate` con `resource_metadata`.
- [x] Token inválido → 401 `invalid_token`.
- [x] El PRM es la única ruta pública (además de `/health`).

## 3. Autorización por scope (tests automatizados)

`cd mcps/trackflow-mcp && .venv/bin/pytest -q` → **35 passed**.

Cubre:

- [x] Token sin `mcp:read` → **403** `missing_required_scopes` antes de MCP.
- [x] Token `mcp:read` invoca una tool de escritura → `INSUFFICIENT_SCOPE`.
- [x] Token `mcp:write` invoca `adjust_inventory_stock` → `INVENTORY_READ_ONLY`
  sin llamar a la API.
- [x] `tools/list` expone nombre, descripción, `inputSchema` y `outputSchema`
  de las 6 tools.
- [x] Un log JSON por invocación con `client_id`, `subject`, `tool`, `outcome`,
  `error_code` y `duration_ms`.

## 4. Datos reales del Incidents Manager y del inventario

Validación directa de las tools contra la API real en `:8002` (misma capa que
usa el MCP):

```text
incident 1: ok=True, status=open, branch=zaragoza_office, category=lost_parcel
summary: open=29, resolved=52, discarded=14; by_branch la_office=47, zaragoza_office=48
inventory CLT-SNK-W-42: current_stock=47, los_angeles=47, zaragoza=0
create_incident: id=96, status=open
update_incident_status: in_progress (PATCH /api/incidents/96/status)
adjust_inventory_stock: INVENTORY_READ_ONLY (sin modificar stock)
```

- [x] La consulta de tickets usa `GET /api/incidents` / `GET /api/incidents/{id}`.
- [x] La creación usa `POST /api/incidents`.
- [x] El cambio de estado usa **solo** `PATCH /api/incidents/{id}/status`.
- [x] La consulta de stock usa `GET /inventory/products` (stock calculado).
- [x] La escritura de inventario se rechaza explícitamente.

### 4.1 Flujo HTTP completo (verificador local, sin Auth0)

Para validar el transporte Streamable HTTP + tools + API real sin depender de
las credenciales M2M, se usó `scripts/local_test_server.py` (solo desarrollo;
acepta `test-read`/`test-write`, nunca en producción) en `:8010`:

```bash
python scripts/local_test_server.py
python scripts/mcp_smoke.py \
  --url http://127.0.0.1:8010/mcp --token test-write \
  --incident-id 1 --write
```

Resultado:

- `tools/list` → 6 tools con `inputSchema` y `outputSchema`.
- `query_incidents` (ticket 1) → incidencia real (`zaragoza_office`, `lost_parcel`).
- `get_incident_summary` → 95 incidencias (29 open / 52 resolved / 14 discarded).
- `query_inventory` → `CLT-SNK-W-42` con 47 unidades en Los Ángeles.
- `adjust_inventory_stock` → `INVENTORY_READ_ONLY` (sin tocar stock).
- `create_incident` → id 96 (`open`).
- `update_incident_status` → id 96 a `in_progress` por el endpoint de ciclo de vida.

Logs reales de la corrida (una línea por tool):

```json
{"event":"tool_invocation","tool":"query_inventory","client_id":"local-test-client","subject":"local-tester","scopes":["mcp:read","mcp:write"],"outcome":"success","error_code":null,"duration_ms":7.03,"arguments":{"sku_code":"CLT-SNK-W-42","limit":20}}
{"event":"tool_invocation","tool":"adjust_inventory_stock","client_id":"local-test-client","subject":"local-tester","scopes":["mcp:read","mcp:write"],"outcome":"error","error_code":"INVENTORY_READ_ONLY","duration_ms":0.01,"arguments":{"sku_id":1,"quantity":1,"operation":"inbound"}}
{"event":"tool_invocation","tool":"update_incident_status","client_id":"local-test-client","subject":"local-tester","scopes":["mcp:read","mcp:write"],"outcome":"success","error_code":null,"duration_ms":3.26,"arguments":{"incident_id":"96","status":"in_progress"}}
```

## 5. Agente migrado al MCP

`cd services/api && venv/bin/python -m pytest tests/test_agent_tools.py tests/test_agent_mcp_failures.py -q`
→ **21 passed**.

- [x] El agente carga las tools con `langchain-mcp-adapters`
  (`MultiServerMCPClient`, `transport="streamable_http"`).
- [x] Se eliminaron `app/agent/tools/incidents.py` y `inventory.py`.
- [x] El enrutado `rag / incident / inventory / +rag` se mantiene.
- [x] MCP caído, timeout, `forbidden`, `not_found` → fallback honesto con
  `status="ok"`; la corrida no falla.
- [x] El RAG no invoca el MCP.
- [x] El token del agente es solo `mcp:read` (sin escritura).

## 6. Pendiente: token M2M y MCPJam

Las credenciales M2M ya están en `mcps/trackflow-mcp/.env`, pero Auth0 devuelve
al pedir el token:

```json
{"error":"access_denied","error_description":"Client has not been granted scopes: mcp:read"}
```

Falta autorizar la app M2M `Test` contra la API del MCP con el scope
`mcp:read`:

1. Auth0 Dashboard → Applications → Applications → app M2M `Test`.
2. Pestaña **APIs** → autorizar la API `TrackFlow MCP` (identifier
   `https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/mcp`).
3. Marcar `mcp:read` (y `mcp:write` solo si se quiere probar escritura con ese
   token) → guardar.
4. Reintentar el smoke.

El resto de comprobaciones necesita además una sesión de navegador en Auth0:

- [ ] `GET /mcp` con token M2M (`mcp:read`) → `tools/list` con las 6 tools.
- [ ] `query_incidents`, `get_incident_summary`, `query_inventory` con token M2M.
- [ ] `create_incident` / `update_incident_status` con token con `mcp:write`.
- [ ] `adjust_inventory_stock` desde MCPJam → `INVENTORY_READ_ONLY`.
- [ ] Captura de MCPJam usando la URL pública de Codespaces (no localhost).
- [ ] Guardar las capturas/JSON en `docs/mcp/playground/`.

Comandos previstos:

```bash
# Token M2M + smoke completo (sin escritura)
cd mcps/trackflow-mcp
.venv/bin/python scripts/mcp_smoke.py \
  --url https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/mcp \
  --token-url https://dev-hfpsbxjc0cragdyx.us.auth0.com/oauth/token \
  --client-id "$AUTH0_M2M_CLIENT_ID" \
  --client-secret "$AUTH0_M2M_CLIENT_SECRET" \
  --audience https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/mcp \
  --scopes "mcp:read"

# Flujo de escritura (create + status)
.venv/bin/python scripts/mcp_smoke.py ... --write
```

MCPJam:

1. `gh codespace ports visibility 8001:public`.
2. Añadir servidor `https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/mcp`.
3. Completar el consentimiento de Auth0.
4. Ejecutar las 6 tools y capturar los resultados.

## 7. Notas operativas

- Subir el **idle timeout** del Codespace antes de la demo para que no se pare.
- No commitear `services/api/data/suppliers.json` (está trackeado y modificado
  por los seeds de la demo).
- `.env` (raíz y `mcps/trackflow-mcp/.env`) está ignorado por git; no contiene
  secretos versionados.
