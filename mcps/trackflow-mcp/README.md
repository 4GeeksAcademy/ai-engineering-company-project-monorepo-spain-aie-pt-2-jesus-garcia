# TrackFlow MCP Server

Servidor MCP de operaciones de TrackFlow. Expone **datos operativos en vivo**
del gestor de incidencias y del inventario a agentes externos, protegido como
**OAuth 2.1 Resource Server** con [`mcpauth`](https://mcp-auth.dev/) (no usa la
capa de auth integrada de FastMCP).

- **Transporte:** Streamable HTTP en `/mcp` (stateless).
- **Autenticación:** JWT bearer validado contra Auth0 (OIDC + JWKS), con
  Protected Resource Metadata en
  `/.well-known/oauth-protected-resource/mcp`.
- **Autorización:** gate `mcp:read` en el middleware + scope por tool
  (`mcp:read` / `mcp:write`).
- **Fuente de datos:** la API REST real de `services/api` (Incidents Manager e
  inventario). No hay datasets simulados ni copias indexadas en el RAG.

```text
MCPJam / cliente OAuth
        │  Bearer JWT (aud = .../mcp, scopes mcp:read|mcp:write)
        ▼
mcps/trackflow-mcp :8001
  ├─ /.well-known/oauth-protected-resource/mcp   (público)
  ├─ /health                                      (público)
  └─ /mcp                                         (mcpauth)
        │  HTTP + JWT de servicio (manager)
        ▼
services/api :8000  →  Incidents Manager / Inventario
```

## Tools

| Tool | Scope | Tipo | Qué hace |
|---|---|---|---|
| `query_incidents` | `mcp:read` | lectura | Busca por `incident_id` o filtros (`status`, `origin`, `branch`, `category`). |
| `get_incident_summary` | `mcp:read` | lectura | Conteos por estado, categoría, origen y sede. |
| `create_incident` | `mcp:write` | escritura | Crea una incidencia real; nace en `open`. |
| `update_incident_status` | `mcp:write` | escritura | Cambia estado vía `PATCH /api/incidents/{id}/status`. |
| `query_inventory` | `mcp:read` | lectura | Stock por SKU/nombre/almacén, calculado desde las órdenes. |
| `adjust_inventory_stock` | `mcp:write` | **guard** | Rechaza siempre cualquier escritura con `INVENTORY_READ_ONLY`. |

Los nombres de campo, IDs y valores de dominio coinciden con `services/api`:

- Estados: `open`, `in_progress`, `resolved`, `discarded`.
- Orígenes: `customer`, `branch`, `internal`.
- Sedes: `central`, `la_warehouse`, `la_office`, `zaragoza_warehouse`, `zaragoza_office`.
- Categorías: `lost_parcel`, `delivery_failure`, `inventory_discrepancy`,
  `carrier_issue`, `returns_issue`, `warehouse_incident`, `system_failure`,
  `client_complaint`, `other`.
- Almacenes: `los_angeles`, `zaragoza`.
- Inventario: `id`, `sku_code`, `name`, `warehouse`, `current_stock`,
  `current_stock_by_warehouse`, `client_id`, `min_stock`.

### Descubrimiento

FastMCP publica nombre, descripción, `inputSchema` y `outputSchema` en
`tools/list`. No hace falta leer el código para descubrir una tool:

```bash
python scripts/mcp_smoke.py --token "$TOKEN" --skip-calls
```

La tool de inventario es de solo lectura. `adjust_inventory_stock` existe para
que un intento de escritura reciba un rechazo explícito y explicable
(`INVENTORY_READ_ONLY`, con `writable: false`), no un error genérico ni un
silencio. No llama a la API ni modifica stock.

## Autenticación OAuth (mcpauth)

`mcpauth` se configura en **modo resource server**:

```python
MCPAuth(
    protected_resources=[
        ResourceServerConfig(
            metadata=ResourceServerMetadata(
                resource=MCP_RESOURCE_URL,          # .../mcp
                authorization_servers=[auth_server_config],
                scopes_supported=["mcp:read", "mcp:write"],
            )
        )
    ]
)
```

- `fetch_server_config(MCP_AUTH_ISSUER, AuthServerType.OIDC)` descubre el issuer
  (Auth0) al arrancar.
- `bearer_auth_middleware("jwt", audience=MCP_RESOURCE_URL,
  resource=MCP_RESOURCE_URL, required_scopes=["mcp:read"])` valida firma,
  `iss`, `aud`, `exp` y el scope base.
- El PRM se sirve en `/.well-known/oauth-protected-resource/mcp` (RFC 9728).
- Los scopes finos se comprueban dentro de cada tool.

> **Dependencia:** se usa `mcpauth==0.2.0b1`. La 0.1.1 estable no incluye
> `protected_resources`, PRM ni el parámetro `resource`.

### Configuración de Auth0

1. Tenant Auth0. Anota el issuer, **con barra final**:
   `https://<tenant>.auth0.com/`.
2. Settings → Advanced:
   - **Resource Parameter Compatibility Profile** ON.
   - **Dynamic Client Registration** ON (para MCPJam).
   - **CIMD** ON (recomendado).
   - **Enable Application Connections** ON.
3. Applications → APIs → Create API:
   - **Identifier** = `MCP_RESOURCE_URL` exacto (`https://<host>-8001.app.github.dev/mcp`).
   - Signing algorithm `RS256`.
   - Permissions: `mcp:read` (Read TrackFlow data) y `mcp:write` (Write TrackFlow data).
   - RBAC ON y **Add Permissions in the Access Token** ON.
   - **Default Permissions for Third-Party Applications**: `mcp:read` + `mcp:write`
     para que el cliente DCR de MCPJam pueda probar todas las tools.
4. Conexión de base de datos habilitada para clientes de terceros; crea un
   usuario de prueba para el consentimiento de MCPJam.
5. Aplicación **Machine to Machine** para el agente:
   - Client ID + Client Secret.
   - Autorizada en la API con `mcp:read` (sin `mcp:write`).
6. Opcional: una segunda app M2M solo-lectura para demostrar
   `INSUFFICIENT_SCOPE` en escritura.

### Códigos de error

| Situación | Capa | Código | Respuesta |
|---|---|---|---|
| Sin `Authorization` | mcpauth | `missing_auth_header` | **401** + `WWW-Authenticate` |
| Token inválido/expirado/firma | mcpauth | `invalid_token` | **401** |
| Issuer incorrecto | mcpauth | `invalid_issuer` | **401** |
| Audiencia incorrecta | mcpauth | `invalid_audience` | **401** |
| Sin scope base `mcp:read` | mcpauth | `missing_required_scopes` | **403** |
| Sin scope de tool | guard | `INSUFFICIENT_SCOPE` | `isError` + JSON |
| Argumentos fuera de esquema | FastMCP | `VALIDATION_ERROR` / JSON-RPC `-32602` | error de protocolo |
| Ticket/SKU inexistente | tool | `NOT_FOUND` | `isError` |
| Transición ilegal | tool | `INVALID_STATUS_TRANSITION` | `isError` |
| Escritura de inventario | tool | `INVENTORY_READ_ONLY` | `isError` |
| API 401/403 (cuenta de servicio) | tool | `BACKEND_AUTH_FAILED` | `isError` |
| API caída / red | tool | `BACKEND_UNAVAILABLE` | `isError` |
| API lenta | tool | `BACKEND_TIMEOUT` | `isError` |
| Fallo inesperado | tool | `INTERNAL_ERROR` | `isError` |

Los errores de tool llevan este cuerpo dentro del texto:

```json
{
  "ok": false,
  "error_code": "INVENTORY_READ_ONLY",
  "message": "El inventario de TrackFlow es de solo lectura en este servidor MCP.",
  "tool": "adjust_inventory_stock",
  "details": {"writable": false}
}
```

## Variables de entorno

Copiar `.env.example` a `.env` (ignorado por git):

| Variable | Obligatoria | Descripción |
|---|---|---|
| `MCP_RESOURCE_URL` | sí | URL pública exacta `.../mcp`; resource del PRM y audience. |
| `MCP_AUTH_ISSUER` | sí | Issuer OIDC (Auth0, barra final). |
| `MCP_AUTH_TYPE` | no | `oidc` (por defecto) u `oauth`. |
| `MCP_BASE_SCOPE` | no | Scope del gate (`mcp:read`). |
| `MCP_SCOPES_SUPPORTED` | no | Lista publicada en el PRM (`mcp:read,mcp:write`). |
| `MCP_ALLOWED_HOSTS` | no | Hosts para la protección anti DNS-rebinding. |
| `MCP_ALLOWED_ORIGINS` | no | Origins permitidos (MCPJam). |
| `TRACKFLOW_API_BASE_URL` | sí | API real (`http://localhost:8000` o `http://services:8000`). |
| `TRACKFLOW_API_EMAIL` / `PASSWORD` | sí* | Cuenta de servicio manager. |
| `TRACKFLOW_API_TOKEN` | alternativa | Token estático; prioridad sobre email/password. |
| `TRACKFLOW_API_TIMEOUT_SECONDS` | no | Timeout de la API (8 s). |
| `MCP_LOG_LEVEL` / `MCP_LOG_FORMAT` | no | `INFO` / `json`. |
| `MCP_DISABLE_DNS_REBINDING_PROTECTION` | no | Solo desarrollo local; no usar en producción. |

\* Si no se define `TRACKFLOW_API_TOKEN`.

## Ejecución local

```bash
cd mcps/trackflow-mcp
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn trackflow_mcp.server:app --host 0.0.0.0 --port 8001
```

La API real debe estar levantada en `:8000` (con incidencias e inventario
sembrados) para que las tools respondan:

```bash
cd services/api
source venv/bin/activate
DATABASE_URL=sqlite:///./dev.db uvicorn app.main:app --port 8000
```

En otra terminal:

```bash
# PRM público
curl -i http://127.0.0.1:8001/.well-known/oauth-protected-resource/mcp

# Sin token → 401 + WWW-Authenticate
curl -i -X POST http://127.0.0.1:8001/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

### Docker Compose

El servicio `mcp` se declara en `docker-compose.yml` (puerto `8001`). Usa la
API por la red Compose (`http://services:8000`) y lee
`mcps/trackflow-mcp/.env`:

```bash
docker compose up -d services mcp
```

### Codespaces + MCPJam

1. Arranca la API y el MCP en el Codespace.
2. Haz público el puerto:
   ```bash
   gh codespace ports visibility 8001:public
   ```
3. Ajusta `MCP_RESOURCE_URL` a la URL reenviada **con `/mcp`** y reinicia:
   ```text
   https://<codespace>-8001.app.github.dev/mcp
   ```
4. Verifica:
   ```bash
   curl -s https://<codespace>-8001.app.github.dev/.well-known/oauth-protected-resource/mcp | jq
   ```
5. En MCPJam, añade el servidor con la URL anterior. El cliente descubre el
   issuer, abre el consentimiento de Auth0 y recibe un token con `mcp:read` +
   `mcp:write`.
6. Ejecuta `scripts/mcp_smoke.py` con el token M2M para la comprobación
   determinista.

## Logs

Cada invocación produce una línea JSON:

```json
{
  "event": "tool_invocation",
  "tool": "query_inventory",
  "client_id": "test-client",
  "subject": "user-1",
  "scopes": ["mcp:read"],
  "outcome": "success",
  "error_code": null,
  "duration_ms": 0.02,
  "arguments": {"sku_code": "CLT-SNK-W-42", "limit": 20}
}
```

Los argumentos se sanean (tokens/secretos → `***`) y se truncan a 200
caracteres. `outcome` es `success`, `error` o `denied`.

## Tests

```bash
cd mcps/trackflow-mcp
.venv/bin/pytest -q
```

Para una prueba HTTP completa sin Auth0 (solo desarrollo, nunca producción):

```bash
python scripts/local_test_server.py            # :8010, acepta test-read/test-write
python scripts/mcp_smoke.py \
  --url http://127.0.0.1:8010/mcp --token test-write --write
```

Cubren:

- PRM público y health.
- 401 sin token, 401 token inválido, 403 sin scope base.
- `tools/list` con esquemas y descripciones.
- `INSUFFICIENT_SCOPE` para escritura con token de lectura.
- `INVENTORY_READ_ONLY` sin llamar a la API.
- Flujos de incidencias e inventario contra un doble de la API.
- Mapeo de errores HTTP de la API.
- Un log por invocación con cliente, tool y resultado.

## Seguridad y límites

- **Mínimo privilegio:** el agente M2M solo recibe `mcp:read`; las escrituras
  requieren `mcp:write` y el cliente de Playground es el único que las prueba.
- **Cuenta de servicio:** la API solo tiene roles `admin/manager/user`; usa un
  usuario `manager` dedicado (`mcp-service@trackflow.com`) en producción, no el
  admin sembrado.
- **Sin escritura de inventario:** el MCP no expone inbound/outbound ni
  discrepancias; esas operaciones viven en el backoffice de operaciones.
- **Sin RAG de tickets:** los tickets cambian en vivo; siempre se consultan por
  API. Indexarlos en Qdrant produciría respuestas obsoletas.
- **Beta de mcpauth:** `0.2.0b1` es la primera versión con resource-server mode;
  está fijada por versión para que un cambio de API no rompa el PRM.
- **Token de servicio:** el JWT local de TrackFlow no se comparte con el MCP;
  el servidor MCP autentica contra la API con su propia cuenta.

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| 401 `invalid_audience` | API identifier de Auth0 no coincide con `MCP_RESOURCE_URL` | Usa la URL exacta con `/mcp`. |
| 401 `invalid_issuer` | `MCP_AUTH_ISSUER` sin barra final o distinto | Copia el `issuer` del discovery de Auth0. |
| 403 `missing_required_scopes` | Token sin `mcp:read` | Incluye `mcp:read` en el client grant/DCR. |
| `INSUFFICIENT_SCOPE` en escritura | Token M2M solo-lectura | Es el comportamiento esperado; usa un token con `mcp:write`. |
| `BACKEND_AUTH_FAILED` | Cuenta de servicio mal configurada o sin rol manager | Revisa `TRACKFLOW_API_EMAIL/PASSWORD` y el rol. |
| 421 `Invalid Host header` | Host público no incluido | Añade el host a `MCP_ALLOWED_HOSTS`. |
| MCPJam no conecta | Puerto privado o DCR desactivado | `gh codespace ports visibility 8001:public`; activa DCR. |
