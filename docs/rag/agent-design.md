# Diseño del agente RAG de TrackFlow (MILESTONE 8)

Grafo de agente sobre la base de conocimiento de TrackFlow con **tools de
lectura en tiempo real** para tickets e inventario. Sustituye la composición
monolítica `query()` por un flujo explícito de nodos con aristas condicionales,
checkpointing y trazas auditables.

- Código: `services/api/app/agent/`
- Tools: `services/api/app/agent/tools/`
- Endpoint: `POST /agent/query` (`services/api/app/routes/agent.py`)
- Evals: `tests/pipelines/test_agent_evals.py`
- Traces de referencia: `tests/pipelines/fixtures/agent_traces/`

## 1. Objetivo

La Parte 1 respondía con la base de conocimiento (procedimientos, políticas,
SLAs), pero no podía responder preguntas sobre el estado real de un ticket o el
stock de un producto. La Parte 2 añade dos tools de **solo lectura** y un
clasificador que decide automáticamente si la pregunta necesita:

- la base de conocimiento (RAG),
- el gestor de incidencias,
- el gestor de inventario,
- o una combinación de una tool + RAG.

Los nodos **reutilizan** `retrieve()` y `generate_answer()` de
`data/pipelines/rag.py`; no se reimplementa el pipeline y ningún nodo invoca
`query()`.

## 2. Flujo

```text
Pregunta
   │
   ▼
receive_question ──(vacía)──────────────────────────► fail ──► END
   │ válida
   ▼
classify  (reglas deterministas)
   ├─ rag ───────────────────────────────────────────► retrieve
   ├─ incident ──────────────────────────────────────► tool_incident
   ├─ inventory ─────────────────────────────────────► tool_inventory
   ├─ incident+rag ──────────────────────────────────► tool_incident ──► retrieve
   └─ inventory+rag ─────────────────────────────────► tool_inventory ─► retrieve

retrieve
   ├─(con contexto)──────────────────────────────────► generate ──► END
   ├─(sin contexto + tool)───────────────────────────► answer_from_tool ──► END
   ├─(error)─────────────────────────────────────────► fail ──► END
   └─(sin contexto)──────────────────────────────────► no_context ──► END

tool_incident / tool_inventory
   ├─(ruta solo tool)────────────────────────────────► answer_from_tool ──► END
   └─(ruta +rag)─────────────────────────────────────► retrieve

generate
   ├─(error)─────────────────────────────────────────► fail ──► END
   └─(ok)────────────────────────────────────────────► END
```

## 3. Estado

`AgentState` (`services/api/app/agent/state.py`) es un `TypedDict` sin
historial de conversación. Además de los campos de la Parte 1
(`question`, `context`, `answer`, `status`, `error`, `run_id`), incluye:

| Campo | Tipo | Para qué |
|---|---|---|
| `user_role` | `str` | Autorizar la tool de tickets (admin/manager). |
| `route` | `Literal[...]` | `rag`, `incident`, `inventory`, `incident+rag`, `inventory+rag`. |
| `routing` | `dict` | Decisión completa del clasificador (argumentos y motivo). |
| `tool_name` | `str` | `incident_lookup` o `inventory_lookup`. |
| `tool_result` | `dict` | Salida tipada de la tool serializada. |
| `tool_status` | `Literal[...]` | `ok`, `not_found`, `timeout`, `unavailable`, `forbidden`, `invalid_input`. |
| `tool_error` | `str \| None` | Código de error de la tool. |
| `fallback` | `bool` | La respuesta se apoya en un fallback honesto. |
| `tool_context_included` | `bool` | El generador recibió el resultado de la tool. |

Cada corrida es stateless: la pregunta actual, la ruta y el resultado de la
tool son suficientes. El detalle de ejecución vive en el trace.

## 4. Nodos

| Nodo | Responsabilidad | Reutiliza |
|---|---|---|
| `receive_question` | Normaliza y valida la pregunta. | — |
| `classify` | Decide RAG / tool / ambos y extrae argumentos. | `router.classify_question` |
| `tool_incident` | Consulta el gestor de incidencias (solo lectura). | `tools.lookup_incident` |
| `tool_inventory` | Consulta stock por producto (solo lectura). | `tools.lookup_inventory` |
| `retrieve` | Recupera chunks por encima de `RAG_MIN_SCORE`. | `rag.retrieve()` |
| `generate` | Redacta con contexto RAG + resultado de tool. | `rag.generate_answer()` |
| `answer_from_tool` | Respuesta determinista con los datos de la tool. | — |
| `no_context` | Respuesta honesta sin LLM. | `rag.NO_CONTEXT_ANSWER` |
| `fail` | Salida terminal segura. | — |

Todos los nodos aceptan dependencias inyectables (`classifier`, `retriever`,
`generator`, `incident_lookup`, `inventory_lookup`) para que los evals los
ejecuten con dobles, sin red ni base de datos.

## 5. Enrutado automático

El clasificador (`app/agent/router.py`) es **determinista** y no hace ninguna
llamada al LLM. Señales principales:

- **Ticket**: `ticket`, `incidencia`, `incident`, `avería`, o un ID
  (`ticket 482`, `#482`, `ticket-482`). Extrae `ticket_id` y filtros de estado
  (`abiertos` → `open`, `en curso` → `in_progress`, etc.) y categoría.
- **Inventario**: `stock`, `inventario`, `existencias`, `SKU`, `disponible`,
  etc. Extrae `sku_code` (`CLT-SNK-W-42`), nombre de producto y almacén
  (`Los Ángeles` / `Zaragoza`).
- **Ambos**: si hay señal de tool y además un término de política (`SLA`,
  `devolución`, `devolver`, `plazo`, `tarifa`, `transportista`,
  `almacenamiento`, `aprobación`...), la ruta es `incident+rag` o
  `inventory+rag`.
- **RAG por defecto**: sin señales de ticket/inventario se consulta la base de
  conocimiento.

La decisión se guarda en el estado (`route`, `routing`) y se traza con un
motivo legible (`reason`). No hay un parámetro de la API para forzar la fuente:
el usuario pregunta en lenguaje natural y el agente decide.

## 6. Tools de lectura en tiempo real

### 6.1 Transporte: MCP Server (Parte 3)

El agente **ya no llama directamente** a `incident_service` ni a
`inventory_service`. Las tools se cargan desde el servidor MCP
[`mcps/trackflow-mcp`](../../mcps/trackflow-mcp/README.md) con
`langchain-mcp-adapters` (Streamable HTTP) y un token OAuth propio
(`client_credentials`). El MCP llama a la API real:

- `query_incidents` → `GET /api/incidents` y `GET /api/incidents/{id}`.
- `get_incident_summary` → `GET /api/incidents/summary`.
- `create_incident` → `POST /api/incidents`.
- `update_incident_status` → `PATCH /api/incidents/{id}/status`.
- `query_inventory` → `GET /inventory/products`.
- `adjust_inventory_stock` → guard que **siempre** rechaza con
  `INVENTORY_READ_ONLY` (no llama a la API).

No existe un dataset paralelo ni datos hardcodeados. El agente solo tiene el
scope `mcp:read`; las escrituras (`mcp:write`) no están disponibles para él.

Los módulos directos `app/agent/tools/incidents.py` y `inventory.py` fueron
eliminados. El único camino es `app/agent/tools/mcp_client.py`.

### 6.2 Contratos

`app/agent/tools/contracts.py` define modelos Pydantic de entrada/salida:

| Tool | Entrada | Salida |
|---|---|---|
| `incident_lookup` | `ticket_id` o filtros (`status`, `category`, `origin`, `branch`) + `limit` | `IncidentRecord` con `id`, `title`, `description`, `origin`, `branch`, `category`, `status`, `created_at`, `updated_at`; error tipado. |
| `inventory_lookup` | `sku_id`, `sku_code` o `name_query` + `warehouse` + `limit` | `InventoryItem` con `current_stock` y `current_stock_by_warehouse`; error tipado. |

Los errores posibles son `invalid_input`, `not_found`, `forbidden`, `timeout`
y `unavailable`. La entrada inválida devuelve un error tipado, nunca una
excepción que tumbe el grafo.

### 6.3 Autenticación y permisos

El endpoint `/agent/query` exige bearer token (`get_current_user`). El rol del
usuario se propaga al estado (`user_role`) y la tool de tickets aplica la misma
autorización que `GET /api/incidents` (`require_manager`): un usuario `user`
recibe un fallback honesto de permisos y no ve datos de tickets.

El agente se autentica contra el MCP con un token OAuth propio
(`MCP_OAUTH_*`, grant `client_credentials`). El JWT local de TrackFlow no se
comparte con el MCP. El servidor MCP, a su vez, usa una cuenta de servicio
`manager` contra la API (`TRACKFLOW_API_EMAIL/PASSWORD` o
`TRACKFLOW_API_TOKEN`).

La autorización de usuario se mantiene en el grafo: la tool de tickets exige
rol `admin`/`manager` antes de invocar el MCP. El scope `mcp:read` del token M2M
es una segunda barrera (mínimo privilegio). La tool de inventario permite
cualquier usuario autenticado, igual que la lectura de
`GET /inventory/products`.

### 6.4 Timeout y fallback

Cada llamada se ejecuta con `ThreadPoolExecutor` y un timeout numérico:

| Variable | Default | Uso |
|---|---|---|
| `AGENT_MCP_TIMEOUT_SECONDS` | `10` | Handshake MCP + tool + API. |

Los timeouts antiguos `AGENT_INCIDENT_TOOL_TIMEOUT_SECONDS` /
`AGENT_INVENTORY_TOOL_TIMEOUT_SECONDS` ya no intervienen en el camino de tools;
se conservan por compatibilidad de configuración.

Si se agota el timeout, la tool devuelve `error="timeout"` y el grafo sigue por
`answer_from_tool`. Los mensajes son honestos:

- ticket no encontrado → "No existe la incidencia X...";
- timeout/servicio caído → "No pude confirmar el estado de ese ticket ahora
  mismo...";
- sin permisos → "No tengo permisos para consultar ese ticket...";
- inventario sin stock → "No tengo constancia de stock para ese producto...".

`answer_from_tool` no llama al LLM: solo formatea el resultado tipado. Así es
imposible que invente un estado o una cantidad cuando la tool falla.

## 7. Compilación y validación estructural

`compile_agent_graph()` se ejecuta **antes de cualquier petición**: el router
llama a `get_agent_graph()` al importarse, así que un grafo inválido impide
arrancar la API. La validación comprueba:

- el estado es un `TypedDict`,
- existe entrada desde `START`,
- no hay aristas hacia nodos inexistentes,
- no hay nodos inalcanzables,
- no hay nodos sin salida salvo los que terminan en `END`.

Los fallos se elevan como `AgentGraphConfigurationError` con el nombre del nodo
problemático.

## 8. Checkpointing

El grafo se compila con `InMemorySaver`. Cada corrida usa
`thread_id = run_id`, por lo que hay un checkpoint por transición. El runner
serializa cada snapshot (estado, `next`, `checkpoint_id`) en el trace.

```python
from services.api.app.agent.graph import get_agent_graph

graph = get_agent_graph()
graph.get_state({"configurable": {"thread_id": run_id}})
graph.get_state_history({"configurable": {"thread_id": run_id}})
```

`InMemorySaver` es local al proceso. Para varios workers o reinicios haría falta
un checkpointer persistente (SQLite/Postgres), sustituible en
`compile_agent_graph(checkpointer=...)` sin tocar nodos ni aristas.

## 9. Trazas

Cada `run_agent()` escribe `{run_id}.json` en `data/eval/agent-traces/`
(configurable con `AGENT_TRACE_DIR`) y añade una línea a `index.jsonl`. El
trace incluye ahora:

- `route`: fuente(s) decidida(s) por el clasificador;
- `sources_used`: fuentes realmente usadas, **en orden**
  (`["incident_tool", "rag"]`, `["rag"]`, `["incident_tool"]`...);
- `node_order`: secuencia exacta de nodos
  (`classify → tool_incident → retrieve → generate`);
- `events`: salida de cada nodo, con `tool_name`, `tool_status`, `found`,
  `fallback` y `elapsed_ms`;
- `checkpoints`: un snapshot por transición.

Ejemplo de una corrida con ticket:

```json
{
  "route": "incident",
  "sources_used": ["incident_tool"],
  "node_order": ["receive_question", "classify", "tool_incident", "answer_from_tool"],
  "events": [
    {"node": "classify", "output": {"route": "incident", "routing": {"ticket_id": 482}}},
    {"node": "tool_incident", "output": {"tool_status": "ok", "fallback": false}},
    {"node": "answer_from_tool", "output": {"status": "ok", "fallback": false}}
  ]
}
```

El resultado de la tool se conserva para auditar el dato exacto, pero la
descripción libre se trunca a 200 caracteres para no volcar textos largos con
posibles datos personales. El rol del usuario no se persiste en el trace.

## 10. Endpoint

`POST /agent/query` (autenticado con bearer token):

```json
{"question": "¿En qué estado está el ticket 482?"}
```

Respuesta `200`:

```json
{"answer": "El ticket 482 está en estado «En curso» (in_progress)...", "run_id": "…"}
```

| Estado del grafo | HTTP | Cuerpo |
|---|---|---|
| `ok` (incluye fallback de tool) | 200 | `{"answer", "run_id"}` |
| `no_context` | 200 | respuesta honesta de `rag.NO_CONTEXT_ANSWER` |
| `invalid_question` | 422 | mensaje de validación |
| `error` / excepción | 502 | mensaje genérico, sin detalle interno |

El contrato HTTP se mantiene estable: la fuente usada se consulta en el trace,
no en la respuesta. `/knowledge/query` sigue existiendo.

## 11. Evals

Un único comando:

```bash
uv run pytest tests/pipelines/test_agent_evals.py -q
```

| Eval | Criterio |
|---|---|
| Pregunta vacía | orden `receive_question → fail`; no se clasifica ni se recupera |
| Orden y contrato RAG | `classify → retrieve → generate`; el generador recibe el contexto recuperado |
| Sin contexto | ruta `classify → retrieve → no_context`; no se llama al LLM |
| **Tool de tickets** | "¿En qué estado está el ticket 482?" → `classify → tool_incident → answer_from_tool`; `sources_used == ["incident_tool"]`; no se usa el RAG |
| **RAG puro** | "¿Cuál es el SLA...?" → `classify → retrieve → generate`; `sources_used == ["rag"]`; no se usan tools |
| **Fallback por timeout** | la tool devuelve `timeout`; respuesta honesta sin estado inventado |
| **No encontrado** | la tool devuelve `not_found`; respuesta honesta |
| **Ambos** | "¿Puedo devolver el paquete del ticket 482?" → `tool_incident → retrieve → generate`; `sources_used == ["incident_tool", "rag"]` |
| **Inventario** | "¿Tenemos stock del SKU...?" → `tool_inventory → answer_from_tool` |
| **Permisos** | un rol `user` no puede leer tickets; fallback de permisos |
| Anclaje (4 casos) | la respuesta cita el dato del BRIEFING y el trace recuperó el documento esperado |
| Checkpoints | 4 transiciones → 4 checkpoints; `get_state` devuelve la respuesta final |
| Compilación | nodo huérfano y estado no tipado fallan con error claro |

Los evals de enrutamiento ejecutan el grafo con stubs y verifican el **trace
persistido**; el de anclaje lee traces reales grabados previamente (sin red).

Para regenerar los fixtures de anclaje (requiere Qdrant indexado y
`services/api/.env`):

```bash
uv run python scripts/record_agent_traces.py
```

## 12. Configuración

| Variable | Default | Uso |
|---|---|---|
| `AGENT_TRACE_DIR` | `data/eval/agent-traces` | Directorio de traces. |
| `AGENT_INCIDENT_TOOL_TIMEOUT_SECONDS` | `3` | Timeout de la tool de tickets. |
| `AGENT_INVENTORY_TOOL_TIMEOUT_SECONDS` | `3` | Timeout de la tool de inventario. |
| `RAG_TOP_K`, `RAG_MIN_SCORE` | 5, 0.35 | Umbrales del `retrieve` reutilizado. |

Dependencia ya presente en la API: `langgraph>=1.2.21`. En Docker hay que
reconstruir la imagen del servicio `api` si se cambian las dependencias.

## 13. Evidencia de la Parte 2

- [`traces/ticket-tool-demo.json`](traces/ticket-tool-demo.json) — corrida real
  con la tool de tickets: `route: "incident"`, `sources_used:
  ["incident_tool"]`.
- [`traces/rag-policy-demo.json`](traces/rag-policy-demo.json) — corrida real
  con RAG: `route: "rag"`, `sources_used: ["rag"]`.
- [`traces/README.md`](traces/README.md) — qué demuestra cada trace y cómo
  regenerarlos.
- [`agent-evals-output-part2.txt`](agent-evals-output-part2.txt) — resultado de
  los evals nuevos (23 passed) y de los tests de tools/contrato (21 passed).
