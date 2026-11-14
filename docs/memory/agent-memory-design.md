# Memoria persistente del agente de TrackFlow

Diseño de la memoria del agente de CX para que las correcciones de carrier, el
contexto operativo recurrente y las preferencias de clientes B2B sobrevivan
entre sesiones. El RAG de la empresa sigue siendo de **solo lectura** y no se
mezcla con la memoria.

- Código: `services/api/app/agent/memory/`
- Endpoint conversacional: `POST /agent/chat`
- Administración: `GET /agent/memory`, `GET /agent/memory/proposals`,
  `POST /agent/memory/proposals/{id}/approve`,
  `POST /agent/memory/{id}/retire`, `POST /agent/memory/consolidate`
- Migración: `services/api/migrations/0004_agent_memory.sql`
- Evidencia: [`agent-memory-evidence.md`](agent-memory-evidence.md)
- Script reproducible: `scripts/demo_agent_memory.py`

---

## 1. Arquitectura elegida y por qué

| Opción | Decisión | Justificación |
|---|---|---|
| **PostgreSQL/Supabase, tablas `agent_memory_*`** | ✅ | Ya existe `DATABASE_URL`, SQLModel y migraciones. Permite auditoría relacional, versionado, TTL, consolidación por `carrier + país + zona` y revisión humana. |
| Redis | ❌ | Es el broker de Celery. No es una fuente de verdad duradera ni permite consultas de auditoría o versionado. Se mantiene solo para tareas asíncronas. |
| Qdrant / colección `*_agent_memory` | ❌ | El volumen es pequeño y estructurado (8 carriers, 2 países, pocos clientes B2B). Un vector store no aporta y complica expiración, versionado y control de envenenamiento. Además, el RAG (`trackflow_knowledge`) queda estrictamente fuera. |
| Knowledge graph | ❌ | Las relaciones relevantes son claves compuestas, no un grafo. 8 carriers y 2 países no justifican la complejidad. |

**Regla no negociable:** ninguna escritura de memoria apunta a
`trackflow_knowledge` ni a una colección `*_knowledge`. La memoria es un store
aparte. Un test de regresión (`test_memory_package_never_references_qdrant_or_
the_knowledge_collection`) comprueba que el paquete no importa Qdrant ni usa
`COLLECTION_NAME`.

### Tipos de memoria que necesita TrackFlow

| Tipo | Qué guarda | Alcance | Caducidad/revisión |
|---|---|---|---|
| `carrier_rule` (semántica) | Cobertura corregida, rutas que dejó de operar, carrier local alternativo. | `carrier + país + zona` | Revisión a 90 días. |
| `operational_context` (episódica) | Huelga, congestión portuaria, retrasos recurrentes con patrón. | `ruta/almacén + país` | TTL 7 días. |
| `client_preference` (semántica B2B) | Formato y métricas destacadas del reporte mensual. | `cliente B2B` | Revisión a 180 días. |

**Descartado:** memoria de conversación ilimitada, direcciones de clientes,
rutas internas de almacén, incidencias de un solo paquete y contratos en
negociación.

---

## 2. Qué nunca entra en la memoria

La validación es determinista y se ejecuta **dos veces**: al proponer y al
escribir. Un fallo nunca escribe una entrada; solo deja un registro de
auditoría con el motivo.

| Categoría | Código | Cobertura |
|---|---|---|
| Dirección exacta de cliente **B2C o B2B** | `exact_address` | Calles/avenidas, números, CP, coordenadas, piso/puerta. Cubre explícitamente marcas y destinatarios finales. |
| Ruta o zona interna del almacén | `internal_warehouse_route` | Pasillos, estanterías, racks, lay-out, muelles, zonas restringidas. |
| Incidencia puntual de un solo paquete | `single_incident` | Tracking, ticket, pedido, `#ID`, “un solo paquete”, “queja aislada” sin marcador de recurrencia. |
| Contrato/tarifa en negociación | `contract_negotiation` | Negociación, pendiente de firma, oferta comercial, descuento/tarifa acordada. |
| Credenciales y datos personales | `credentials`, `personal_data_email`, `personal_data_phone` | Passwords, tokens, API keys, emails, teléfonos. |
| Instrucciones embebidas | `prompt_injection` | “Ignora las instrucciones”, “system prompt”, “regla permanente”, etc. |

Además, el prompt del LLM enumera las mismas prohibiciones. La memoria se trata
como **datos, no instrucciones**: se ignora cualquier instrucción que aparezca
dentro de ella.

### Ejemplos documentados

**Sí generan propuesta**

1. “En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que usar el
   carrier local desde el mes pasado.”
2. “Esos retrasos reportados en incidencias de Los Ángeles esta semana son por
   la huelga portuaria, no por un problema nuestro — ya van tres tickets sobre
   lo mismo.”
3. “El cliente de cosméticos siempre quiere su reporte mensual con el desglose
   de devoluciones primero, antes que el volumen de envíos.”

**No generan propuesta**

1. “¿Dónde está el paquete con tracking XJ4471?” — consulta puntual.
2. “Perfecto, ya quedó resuelto.” — cierre de conversación.
3. “Tradúceme esto al inglés para el cliente.” — tarea de un solo uso.
4. “¿Cuál es el SLA de un envío estándar?” — pregunta de política.
5. “Gracias, muy amable.” — cortesía.

---

## 3. Modelo de datos

### `agent_memory_entries`

Hecho aprobado. Campos principales: `memory_type`, `scope_type`, `scope_key`
(canónico), `scope_label`, `scope_json`, `fact`, `reason`, `status`, `version`,
`supersedes_id`, `source_proposal_id`, `created_by`, `approved_by`,
`created_at`, `updated_at`, `expires_at`, `review_at`.

- Índice único parcial **`ux_agent_memory_active_scope`**: una sola entrada
  `active` por `scope_key`.
- Una corrección nueva marca la anterior como `superseded` e inserta la nueva
  con `version + 1` y `supersedes_id`. El histórico no se borra.
- Estados: `active`, `superseded`, `expired`, `stale`, `retired`, `blocked`.

### `agent_memory_proposals`

Propuesta y registro de decisión. Guarda `memory_type`, alcance, hecho,
`source_quote` (cita literal), `status`, `decision_label`,
`decision_confidence`, `decision_message` (saneado), `decision_at`,
`resulting_entry_id`, `validation_code` y `created_at`/`expires_at`.

- Índice único parcial **`ux_agent_memory_pending_user`**: una sola propuesta
  `pending` por usuario. La regla “una a la vez” se refuerza en base de datos.
- Estados: `pending`, `approved`, `rejected`, `edited`, `blocked`, `expired`.

### `agent_memory_audit`

Log append-only: acción, actor, sesión, propuesta, entrada, mensaje origen
**saneado**, hash del mensaje y detalle JSON. Registra propuestas, decisiones,
bloqueos por validación, expiraciones, supersesiones, retiradas y
consolidaciones. Se conserva tanto si la propuesta fue aprobada como si fue
rechazada.

---

## 4. Interfaz explícita de lectura/escritura

El agente **no acumula estado en el system prompt**. La única puerta es
`app/agent/memory/store.py`:

| Función | Responsabilidad |
|---|---|
| `read_memory(question)` | Devuelve un bloque acotado (máx. 12 entradas / 4.000 caracteres) de entradas `active`, no caducadas, no obsoletas y relevantes por solapamiento de tokens. |
| `create_proposal(...)` | Valida y crea una propuesta `pending`. No escribe en `entries`. Si ya hay una pendiente, la omite y lo audita. |
| `resolve_proposal(...)` | Aplica la decisión (`approve`/`reject`/`edit`/`unrelated`), escribe o rechaza, versiona y audita. |
| `expire_stale_proposals(...)` | Caduca propuestas sin respuesta (TTL por defecto 24 h). |
| `consolidate(...)` | Expira, marca obsoletas, deduplica, bloquea filas legacy prohibidas y aplica el tope de activas. |
| `retire_entry(...)` | Retirada manual por manager/admin, con auditoría. |

La lectura se hace **antes** de la corrida del grafo y se pasa como
`memory_context` en el estado. El grafo no abre conexiones a base de datos.

---

## 5. Auto-evaluación y propuesta en la misma conversación

### Ruta RAG (`generate`)

Una **única llamada** al LLM devuelve la respuesta visible y, si aplica, la
propuesta:

```json
{
  "respuesta": "texto para el usuario",
  "propuesta_memoria": null | {
    "tipo": "carrier_rule | operational_context | client_preference",
    "alcance": {
      "tipo": "carrier | ops | client",
      "carrier": "SEUR", "pais": "ES", "zona": "rural",
      "sitio": "los_angeles | zaragoza", "corredor": "...",
      "cliente": "..."
    },
    "hecho": "...",
    "motivo": "...",
    "cita_origen": "frase literal del mensaje del usuario"
  }
}
```

No hay segundo agente ni segunda llamada en esta ruta. Si el JSON se rompe, la
respuesta cae a texto plano y no se propone memoria; nunca se escribe a ciegas.

### Rutas deterministas (`tool`/`no_context`)

Las consultas puras de ticket/stock siguen sin LLM. Solo si un **gate
determinista** detecta un enunciado memorizable (corrección, preferencia,
recurrencia, “en realidad”, “ya no”, “son por”, “siempre quiere”...) se hace
**una** llamada de evaluación. Como en esa ruta no hubo generación, no es una
segunda llamada. El gate también descarta cierres, cortesías, preguntas puras y
tareas de un solo uso.

La respuesta final se construye igualmente sin LLM; la evaluación solo produce
la propuesta.

### Propuesta visible

El servicio añade a la respuesta, en el mismo turno:

> ¿Quieres que lo recuerde para futuras conversaciones? Responde «sí» para
> guardarlo o «no» para descartarlo.

La respuesta HTTP incluye además `memory.pending_proposal` con id, tipo,
alcance, hecho y pregunta. El cliente puede renderizarlo como tarjeta.

---

## 6. Confirmación del usuario y auditoría

Cuando hay una propuesta pendiente, el siguiente mensaje se evalúa primero con
un **clasificador de intención estructurado** (LLM + Pydantic), nunca con
`"sí" in mensaje`:

| Etiqueta | Significado | Efecto |
|---|---|---|
| `approve` | Acepta la propuesta tal cual. | Escribe/versiona la entrada. |
| `reject` | La rechaza claramente. | No escribe; auditoría `rejected`. |
| `edit` | Acepta con cambios de hecho/alcance. | Revalida la edición, escribe la versión editada y audita `edited`. |
| `unrelated` | Cambia de tema, ambigüedad, silencio o no se refiere a la propuesta. | **Rechazo por defecto** y la conversación sigue con el nuevo tema. |

- **Fallo en cerrado:** error del modelo, JSON inválido o confianza < 0,6 →
  `unrelated` → rechazo. Nunca aprobación por silencio o ambigüedad.
- **Una sola propuesta pendiente por usuario** (índice único en BD). Si ya hay
  una, no se crea una segunda; se audita `proposal_skipped`.
- **Aprobación + nueva pregunta en el mismo mensaje:** el clasificador devuelve
  `pregunta_restante`; se resuelve la propuesta y se responde a la pregunta en
  el mismo turno.
- **Propuesta sin respuesta:** caduca a las 24 h (`AGENT_MEMORY_PROPOSAL_TTL_
  HOURS`) y se marca `expired`. El siguiente mensaje se responde con
  normalidad.
- **Edición inválida** (cita no literal, contenido prohibido): se rechaza y no
  se escribe nada.

Cada decisión queda en `agent_memory_proposals` (propuesta, resultado, mensaje,
confianza, timestamp) y en `agent_memory_audit`. La consulta de auditoría está
en `GET /agent/memory/proposals` (manager/admin).

---

## 7. Anti-envenenamiento

1. **Ninguna escritura automática:** solo tras una decisión explícita del
   usuario en el turno siguiente.
2. **Cita literal obligatoria:** la propuesta debe incluir `cita_origen`, una
   subcadena literal del mensaje del usuario. Si no aparece, se rechaza. Esto
   impide que el LLM invente una “corrección” a partir del contexto RAG o de una
   tool.
3. **Solo el mensaje del usuario es fuente:** el prompt prohíbe proponer hechos
   extraídos del RAG o de resultados de tools.
4. **Alcance obligatorio y acotado:** no existe memoria global; el daño máximo
   queda limitado a un carrier/país/zona o a un cliente.
5. **Validación determinista** de contenido prohibido y PII, en dos fases.
6. **Procedencia, versión y reversibilidad:** autor, aprobador, `supersedes_id`,
   auditoría y retirada manual.
7. **Caducidad y revisión:** lo volátil decae; lo estable se revisa. Una entrada
   obsoleta o caducada no se inyecta.
8. **La memoria no son instrucciones:** se delimita y se ignora cualquier
   instrucción embebida.
9. **Conflicto con la política curada:** si la memoria aprobada contradice el
   `CONTEXTO`, el prompt prioriza la corrección humana para ese alcance y pide
   señalar que la base de conocimiento puede estar desactualizada.
10. **Gate de roles opcional:** `AGENT_MEMORY_POLICY_APPROVER_ROLES` permite
    exigir manager/admin para reglas de carrier o contexto operativo sin tocar
    código. Por defecto está vacío (flujo del brief: cualquier usuario
    autenticado).

---

## 8. Consolidación, olvido y expiración

| Política | Valor por defecto | Por qué |
|---|---|---|
| TTL de contexto operativo | 7 días | Una huelga o congestión deja de ser cierta rápido; recordarla indefinidamente provoca respuestas obsoletas. |
| Revisión de regla de carrier | 90 días | La cobertura cambia con los contratos; se conserva hasta la revisión, luego pasa a `stale` y deja de usarse. |
| Revisión de preferencia B2B | 180 días | Las preferencias de reporting son estables, pero pueden cambiar con la relación comercial. |
| TTL de propuesta pendiente | 24 h | El silencio no es aprobación; la propuesta caduca. |
| Tope de entradas activas | 200 | Evita crecimiento sin control; primero expulsa lo episódico y lo más antiguo. |

`consolidate()`:

1. Caduca propuestas pendientes vencidas.
2. Expira entradas con `expires_at` pasado.
3. Marca `stale` las que superan `review_at`.
4. Bloquea filas legacy que contengan contenido prohibido.
5. Deduplica por `scope_key` (deja la versión más reciente).
6. Aplica el tope de activas.

Se ejecuta tras cada escritura y desde el CLI
(`python -m app.agent.memory.consolidation`) y el endpoint de manager.

**Olvido manual:** `POST /agent/memory/{id}/retire` retira una entrada con
auditoría. **Olvido por corrección:** una nueva regla supersede la anterior; el
histórico queda versionado, pero solo la activa se lee.

---

## 9. ¿Por qué no hace falta una arquitectura multi-agente?

Porque la auto-evaluación es **un campo más de la misma salida estructurada**
del generador (`respuesta` + `propuesta_memoria`), y la confirmación es un
clasificador de intención sobre una propuesta que ya vive en el store. No hay
un agente “memoria” separado, ni un orquestador, ni una segunda generación en la
ruta RAG. En las rutas deterministas hay como máximo **una** llamada de
evaluación, que es la única del turno (no había generación). El estado de la
propuesta pendiente está en PostgreSQL, no en un proceso aparte. Un
multi-agente añadiría latencia, coste, puntos de fallo y un problema de
consistencia entre la respuesta y la propuesta sin aportar nada al caso de uso.

---

## 10. Endpoints y configuración

```http
POST /agent/chat
{"message": "...", "session_id": "opcional"}
→ {"session_id", "run_id", "answer", "memory": {
     "pending_proposal": null | {...},
     "resolution": null | {...},
     "blocked": null | "exact_address" | ...
  }}

GET  /agent/memory                     # cualquier usuario autenticado
GET  /agent/memory/proposals           # manager/admin
POST /agent/memory/proposals/{id}/approve  # manager/admin (validación de rol)
POST /agent/memory/{entry_id}/retire   # manager/admin
POST /agent/memory/consolidate         # manager/admin
```

`/agent/query` se mantiene intacto para consumidores stateless.

Variables de entorno (todas con default; no se ha tocado `.env.example` porque
está protegido):

| Variable | Default |
|---|---|
| `AGENT_MEMORY_ENABLED` | `1` |
| `AGENT_MEMORY_EPISODIC_TTL_DAYS` | `7` |
| `AGENT_MEMORY_CARRIER_REVIEW_DAYS` | `90` |
| `AGENT_MEMORY_CLIENT_REVIEW_DAYS` | `180` |
| `AGENT_MEMORY_PROPOSAL_TTL_HOURS` | `24` |
| `AGENT_MEMORY_MAX_CONTEXT_ENTRIES` | `12` |
| `AGENT_MEMORY_MAX_CONTEXT_CHARS` | `4000` |
| `AGENT_MEMORY_MAX_ACTIVE_ENTRIES` | `200` |
| `AGENT_MEMORY_INTENT_MIN_CONFIDENCE` | `0.6` |
| `AGENT_MEMORY_POLICY_APPROVER_ROLES` | vacío (todos) |
| `AGENT_MEMORY_POLICY_MEMORY_TYPES` | `carrier_rule,operational_context` |

---

## 11. Limitaciones y siguientes pasos

- La relevancia de lectura es por solapamiento de tokens, no embeddings. Es
  deliberado por volumen y auditabilidad; si el store crece a cientos de
  entradas por cliente, se puede añadir un índice semántico **sobre el store de
  memoria**, nunca sobre `*_knowledge`.
- La migración `0004` está preparada pero **no se aplica automáticamente** en
  Supabase; el procedimiento es el de `migrations/README.md` (backup + conexión
  directa 5432 + verificación).
- No hay UI de chat en esta entrega (el alcance acordado es backend + docs +
  tests). El contrato HTTP ya devuelve la tarjeta de propuesta y la resolución.
- El gate de roles para reglas de carrier está implementado y desactivado por
  defecto; activarlo es una decisión de despliegue.
- La traza del agente y la auditoría redactan PII; el mensaje original completo
  no se persiste en claro cuando contiene datos prohibidos.

---

## 12. Cómo verificar

```bash
# Tests de la API (store, validación, gate, intención, chat, endpoints)
cd services/api && source venv/bin/activate
python -m pytest tests/test_agent_memory.py tests/test_agent_chat.py -q

# Suite completa de la API
python -m pytest -q

# Evals del grafo (existentes + memoria)
cd ../..
uv run pytest tests/pipelines/test_agent_evals.py \
  tests/pipelines/test_agent_memory_evals.py -q

# Evidencia reproducible (sin red, sin LLM, sin Qdrant)
services/api/venv/bin/python scripts/demo_agent_memory.py
```
