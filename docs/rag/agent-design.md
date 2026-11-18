# Diseño del agente RAG de TrackFlow (MILESTONE 8)

Grafo de agente sobre la base de conocimiento de TrackFlow. Sustituye la
composición monolítica `query()` por un flujo explícito de nodos con aristas
condicionales, checkpointing y trazas auditables.

- Código: `services/api/app/agent/`
- Endpoint: `POST /agent/query` (`services/api/app/routes/agent.py`)
- Evals: `tests/pipelines/test_agent_evals.py`
- Traces de referencia: `tests/pipelines/fixtures/agent_traces/`

## 1. Objetivo

El RAG del MILESTONE 7 ya respondía con datos del BRIEFING, pero su composición
`query() = retrieve() + generate_answer()` no permitía ver ni decidir el camino
seguido. Este milestone hace explícitos tres pasos con responsabilidad única:

1. recibir y validar la pregunta,
2. recuperar contexto de Qdrant,
3. generar la respuesta con ese contexto (o responder con honestidad si no hay).

Los nodos **reutilizan** `retrieve()` y `generate_answer()` de
`data/pipelines/rag.py`; no se reimplementa ni se duplica el pipeline, y ningún
nodo invoca `query()`.

## 2. Flujo

```text
Pregunta
   │
   ▼
receive_question ──(vacía)──────────────────────────► fail ──► END
   │ válida
   ▼
retrieve  (data.pipelines.rag.retrieve)
   ├──(error)──────────────────────────────────────► fail ──► END
   ├──(sin contexto sobre el umbral)────────────────► no_context ──► END
   └──(con contexto)
          ▼
      generate  (data.pipelines.rag.generate_answer)
          ├──(error)────────────────────────────────► fail ──► END
          └──(ok)───────────────────────────────────► END
```

## 3. Estado

`AgentState` (`services/api/app/agent/state.py`) es un `TypedDict` con seis
campos y **sin historial de conversación**:

| Campo | Tipo | Para qué |
|---|---|---|
| `question` | `str` | Pregunta normalizada; la usa retrieve y generate. |
| `context` | `list[dict]` | Payloads de Qdrant que produce `retrieve`. |
| `answer` | `str` | Respuesta final o mensaje seguro de error. |
| `status` | `Literal[...]` | `ok`, `invalid_question`, `no_context`, `error`. |
| `error` | `str \| None` | Mensaje apto para el cliente (sin stack traces). |
| `run_id` | `str` | Correlación con el trace y `thread_id` del checkpointer. |

Cada corrida es stateless: el RAG solo necesita la pregunta actual y el
contexto recuperado. Los detalles de ejecución viven en el trace, no en el
estado.

## 4. Nodos

| Nodo | Responsabilidad | Reutiliza |
|---|---|---|
| `receive_question` | Normaliza y valida la pregunta. | — |
| `retrieve` | Recupera chunks por encima de `RAG_MIN_SCORE`. | `rag.retrieve()` |
| `generate` | Redacta la respuesta usando el contexto ya recuperado. | `rag.generate_answer()` |
| `no_context` | Responde honestamente sin llamar al LLM. | `rag.NO_CONTEXT_ANSWER` |
| `fail` | Salida terminal segura para pregunta inválida o fallo interno. | — |

Los nodos `retrieve` y `generate` aceptan dependencias inyectables
(`make_retrieve_node(retriever=...)`) para que los evals los ejecuten con
dobles de prueba, sin red.

## 5. Aristas condicionales

Las transiciones se deciden en funciones puras (`route_after_receive`,
`route_after_retrieve`, `route_after_generate`), no con una secuencia fija:

- pregunta vacía → `fail` (nunca se recupera),
- `retrieve` con error → `fail`,
- `retrieve` sin chunks sobre el umbral → `no_context` (nunca se genera sobre
  contexto vacío),
- `generate` con error → `fail`.

## 6. Compilación y validación estructural

`compile_agent_graph()` se ejecuta **antes de cualquier petición**: el router
llama a `get_agent_graph()` al importarse, así que un grafo inválido impide
arrancar la API. La validación comprueba:

- el estado es un `TypedDict`,
- existe entrada desde `START`,
- no hay aristas hacia nodos inexistentes,
- no hay nodos inalcanzables (p. ej. un nodo huérfano),
- no hay nodos sin salida salvo los que terminan en `END`.

Los fallos se elevan como `AgentGraphConfigurationError` con el nombre del nodo
problemático.

## 7. Checkpointing

El grafo se compila con `InMemorySaver`. Cada corrida usa
`thread_id = run_id`, por lo que hay un checkpoint por transición:

```python
from services.api.app.agent.graph import get_agent_graph

graph = get_agent_graph()
graph.get_state({"configurable": {"thread_id": run_id}})
graph.get_state_history({"configurable": {"thread_id": run_id}})
```

El runner serializa además cada snapshot (estado, `next`, `checkpoint_id`) en el
trace, de modo que la traza permite inspeccionar la corrida sin mantener el
proceso vivo. `get_run_state(run_id)` devuelve el último estado guardado.

`InMemorySaver` es local al proceso: sirve para inspeccionar y retomar dentro
de la vida del proceso. Para varios workers o reinicios haría falta un
checkpointer persistente (SQLite/Postgres), sustituible en
`compile_agent_graph(checkpointer=...)` sin tocar nodos ni aristas.

## 8. Trazas

Cada `run_agent()` escribe `{run_id}.json` en `data/eval/agent-traces/`
(configurable con `AGENT_TRACE_DIR`) y añade una línea a `index.jsonl`:

```json
{
  "run_id": "…",
  "question": "¿Cuánto tarda un envío estándar?",
  "status": "ok",
  "answer": "…",
  "node_order": ["receive_question", "retrieve", "generate"],
  "events": [
    {"seq": 0, "node": "receive_question", "next_nodes": ["retrieve"], "output": {"status": "ok"}},
    {"seq": 1, "node": "retrieve", "next_nodes": ["generate"], "output": {"context_count": 5, "sources": ["…"]}},
    {"seq": 2, "node": "generate", "next_nodes": [], "output": {"answer": "…", "status": "ok"}}
  ],
  "checkpoints": [{"step": 0, "checkpoint_id": "…", "next_nodes": ["retrieve"], "values": {}}]
}
```

Se leen con `AgentTrace.load(path)` o `AgentTrace.load_latest(dir)`. El trace
guarda el contexto recuperado (documento, sección y texto) para poder auditar
el anclaje de la respuesta.

## 9. Endpoint

`POST /agent/query` (autenticado con bearer token):

```json
{"question": "¿Cuál es el SLA de un envío estándar?"}
```

Respuesta `200`:

```json
{"answer": "…", "run_id": "…"}
```

| Estado del grafo | HTTP | Cuerpo |
|---|---|---|
| `ok` | 200 | `{"answer", "run_id"}` |
| `no_context` | 200 | respuesta honesta de `rag.NO_CONTEXT_ANSWER` |
| `invalid_question` | 422 | mensaje de validación |
| `error` / excepción | 502 | mensaje genérico, sin detalle interno |

El endpoint no contiene lógica de negocio: invoca `run_agent()` y traduce el
estado final. `/knowledge/query` se mantiene intacto por compatibilidad.

## 10. Evals

Un único comando:

```bash
uv run pytest tests/pipelines/test_agent_evals.py -q
```

| Eval | Criterio |
|---|---|
| Pregunta vacía | orden `receive_question → fail`; retrieve y generate no se ejecutan |
| Orden y contrato | `retrieve` antes de `generate`; el generador recibe exactamente el contexto recuperado |
| Sin contexto | ruta `retrieve → no_context`; no se llama al LLM |
| Anclaje (4 casos) | la respuesta cita el dato del BRIEFING (`3 a 5 días hábiles`, `40%`, `gestión manual`, `Miguel Torres`) y el trace recuperó el documento esperado |
| Checkpoints | 3 transiciones → 3 checkpoints; `get_state` devuelve la respuesta final |
| Compilación | nodo huérfano y estado no tipado fallan con error claro |

Los evals de enrutamiento ejecutan el grafo con stubs y verifican el **trace
persistido**; el de anclaje lee traces reales grabados previamente (sin red).

Para regenerar los fixtures de anclaje (requiere Qdrant indexado y
`services/api/.env`):

```bash
uv run python scripts/record_agent_traces.py
```

## 11. Configuración

| Variable | Default | Uso |
|---|---|---|
| `AGENT_TRACE_DIR` | `data/eval/agent-traces` | Directorio de traces. |
| `RAG_TOP_K`, `RAG_MIN_SCORE` | 5, 0.35 | Umbrales del `retrieve` reutilizado. |

Dependencia añadida a la API: `langgraph>=1.2.21` (ya presente en el
`pyproject.toml` raíz). En Docker hay que reconstruir la imagen del servicio
`api` para instalarla.
