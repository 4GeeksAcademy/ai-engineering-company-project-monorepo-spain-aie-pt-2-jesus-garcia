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
- [x] `GET /.well-known/oauth-protected-resource` (sin `/mcp`) → **404**
  explícito, no 401, para no confundir a clientes que prueban la raíz.

## 1.1 Validación en Codespaces (URL pública)

Servidor arrancado dentro del Codespace y puerto `8001` con visibilidad
pública (`gh codespace ports visibility 8001:public`):

```text
GET https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/.well-known/oauth-protected-resource/mcp
→ 200, resource=.../mcp, authorization_servers=[Auth0], scopes=[mcp:read,mcp:write]

POST https://.../mcp sin Authorization
→ 401, WWW-Authenticate: Bearer ... resource_metadata="https://.../.well-known/oauth-protected-resource/mcp"
```

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

Fallback real en el Codespace antes del grant M2M: `POST /agent/query`
devolvió **200** con un mensaje honesto, sin romper el grafo. Tras conceder el
grant, las mismas preguntas devuelven datos reales (ver §6.1).

## 6. Token M2M y MCPJam

### 6.1 Token M2M (validado)

El client grant de la app `TrackfFow MCP (Test Application)` ya incluye
`mcp:read` y `mcp:write`. El token emitido lo confirma:

```json
{"access_token":"...","expires_in":86400,"token_type":"Bearer","scope":"mcp:read mcp:write"}
```

Smoke completo contra la URL pública del Codespace:

```bash
python scripts/mcp_smoke.py \
  --url https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/mcp \
  --scopes "mcp:read mcp:write" --incident-id 1 --write
```

Resultados:

- [x] `tools/list` → 6 tools con schemas.
- [x] `query_incidents` ticket 1 → incidencia real (`zaragoza_office`, `lost_parcel`, `open`).
- [x] `get_incident_summary` → 95 incidencias.
- [x] `query_inventory` → `CLT-SNK-W-42` con 47 uds.
- [x] `adjust_inventory_stock` → `INVENTORY_READ_ONLY` sin tocar stock.
- [x] `create_incident` → incidencia 96 (`open`).
- [x] `update_incident_status` → 96 a `in_progress` por `PATCH /api/incidents/96/status`.

Agente real en el Codespace (admin/manager contra `POST /agent/query`):

```text
"¿En qué estado está el ticket 1?"
→ 200, "El ticket 1 está en estado «Abierto» (open)... Oficina de Zaragoza..."

"¿Tenemos stock de CLT-SNK-W-42?"
→ 200, "47 unidades en total (Los Ángeles: 47, Zaragoza: 0)"
```

Esto confirma que el agente ya consulta el Incidents Manager y el inventario
reales a través del MCP, sin camino directo.

### 6.2 MCPJam (discovery validado; ejecución pendiente)

- [x] Conexión de MCPJam a la URL pública del Codespace
  (`https://bookish-guacamole-9j95xrv6qpwf9p99-8001.app.github.dev/mcp`).
- [x] Discovery de las **6 tools** con nombre, descripción y scopes. Captura:
  [`docs/mcp/playground/mcpjam-discovery.png`](../../docs/mcp/playground/mcpjam-discovery.png).
- [ ] Ejecutar las 6 tools desde el Playground y guardar los resultados.

El navegador automatizado de esta sesión no pudo completar el popup de login de
MCPJam (su backend devolvía 401 de sesión guest); la sesión del usuario sí
conectó y descubrió las tools. El flujo determinista equivalente —mismas tools,
mismo servidor público, mismo OAuth— está validado con el token M2M en §6.1:
ticket 1, summary, stock, guard `INVENTORY_READ_ONLY`, creación y transición de
estado.

## 7. Notas operativas

- Subir el **idle timeout** del Codespace antes de la demo para que no se pare.
- No commitear `services/api/data/suppliers.json` (está trackeado y modificado
  por los seeds de la demo).
- `.env` (raíz y `mcps/trackflow-mcp/.env`) está ignorado por git; no contiene
  secretos versionados.
