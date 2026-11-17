# Chat en tiempo real por WebSocket — Diseño

Implementación de la Parte 2 del canal en tiempo real: el **First-line CX agent**
(`first_line_cx`) responde por un WebSocket persistente, token a token, y el
cliente puede interrumpir la respuesta para redirigir la conversación. Este
canal es independiente del SSE de notificaciones RFP de la Parte 1: no comparte
router, bus ni payloads.

## 1. Arquitectura

```
Cliente (1..N pestañas/supervisores)
   │  ws://…/chat/ws?session_id=chat_0219&token=<JWT>
   ▼
GET /chat/ws ── auth JWT ── ChatSession existente + ownership
   │
   ├─ subscribe("chat.<session_id>") ──────────────┐
   │                                               │
   │  user_message / interrupt_requested           │  eventos
   ▼                                               │
ChatService ── GenerationRegistry (1/sesión)       │
   │                                               │
   └─ asyncio task → threadpool → chat()           │
           └─ LangGraph stream_mode="custom"       │
                 └─ tokens ── publish ─────────────┘
```

- **Productor**: un único turno activo por sesión. Ejecuta el agente existente
  (`app/agent/memory/service.chat`) y publica cada token.
- **Consumidores**: cada conexión WebSocket se suscribe al canal
  `chat.<session_id>` y recibe su copia. El productor no conoce sockets.
- **Persistencia**: `chat_sessions` y `chat_messages` (SQLModel). La sesión es
  también el `thread_id` del checkpointer de LangGraph.

Código:

| Ruta | Responsabilidad |
|---|---|
| `services/api/app/chat/models.py` | Tablas `ChatSession` y `ChatMessage`. |
| `services/api/app/chat/store.py` | Persistencia, historial, parciales y reconciliación. |
| `services/api/app/chat/bus.py` | Pub/sub en memoria con canal por sesión. |
| `services/api/app/chat/generations.py` | Generación activa, lock de emisión y aborto. |
| `services/api/app/chat/service.py` | Turnos, streaming, interrupción y cierre. |
| `services/api/app/routes/chat.py` | REST de sesiones + endpoint WebSocket. |
| `services/api/app/agent/memory/streaming.py` | Extractor incremental del campo `respuesta`. |
| `services/api/app/agent/memory/llm.py` | `chat_json_stream` (SSE OpenAI-compatible). |
| `services/api/app/agent/streaming.py` | Contexto de aborto y streaming por corrida. |
| `uis/backoffice/app/(protected)/chat/` | Interfaz de chat. |
| `uis/backoffice/lib/chat-socket.ts` | WebSocket + backoff + watchdog. |
| `uis/backoffice/lib/chat-types.ts` | Contrato y reducer append-only. |

## 2. Entidades y campos

`ChatSession` (BRIEFING §3):

| Campo | Valor |
|---|---|
| `session_id` | `chat_<10 hex>`; **es también el `thread_id`** |
| `agent_id` | `first_line_cx` |
| `user_id` | usuario autenticado |
| `client_id` | opcional, enviado al crear la sesión |
| `status` | `active` / `interrupted` / `closed` |
| `created_at` | UTC ISO-8601 |

`ChatMessage`: `message_id` (`msg_…`), `session_id`, `role`
(`user`/`assistant`), `text`, `status` (`streaming`/`completed`/`interrupted`/
`failed`), `sequence` (orden del token dentro del mensaje), `run_id`,
`created_at`.

## 3. Contrato WebSocket

Cliente → servidor:

```json
{"event":"user_message","data":{"session_id":"chat_0219","text":"…"}}
{"event":"interrupt_requested","data":{"session_id":"chat_0219","new_input":"espera, quiero una devolución"}}
{"event":"pong","data":{"session_id":"chat_0219"}}
```

Servidor → cliente:

```json
{"event":"session_snapshot","data":{"session_id":"chat_0219","thread_id":"chat_0219","agent_id":"first_line_cx","status":"active","messages":[],"active_generation":null}}
{"event":"user_message","data":{"session_id":"chat_0219","message_id":"msg_0448","text":"…"}}
{"event":"generation_started","data":{"session_id":"chat_0219","message_id":"msg_0449","run_id":"…"}}
{"event":"token_chunk","data":{"session_id":"chat_0219","message_id":"msg_0449","run_id":"…","token":"Tu","sequence":7}}
{"event":"interrupt_requested","data":{"session_id":"chat_0219","message_id":"msg_0449","new_input":"…"}}
{"event":"generation_interrupted","data":{"session_id":"chat_0219","message_id":"msg_0449","status":"interrupted","text":"parcial mostrado","sequence":7}}
{"event":"generation_completed","data":{"session_id":"chat_0219","message_id":"msg_0450","run_id":"…","status":"ok","blocked":false,"text":"respuesta completa"}}
{"event":"error","data":{"session_id":"chat_0219","code":"…","message":"…"}}
{"event":"ping","data":{"session_id":"chat_0219"}}
```

- `generation_started` y `ping` son auxiliares; los seis eventos del BRIEFING
  mantienen nombre y campos.
- `generation_completed.blocked` solo es `true` si el output guard sustituyó
  una respuesta ya empezada a streamear. Es la única excepción al render
  append-only (corrección de seguridad).
- No se reutiliza ningún nombre ni payload de las notificaciones RFP de la
  Parte 1.

## 4. Autenticación y binding

- **Mismo JWT** que el backoffice y el SSE. `authenticate_token()` se comparte
  con `get_current_user` (misma caché de 5 s).
- Handshake preferente: `?token=<JWT>&session_id=<chat_…>`. El token se valida
  **antes** de aceptar; sin token o inválido se rechaza (HTTP 403 / cierre
  4401) sin entregar eventos.
- También se admite un primer frame
  `{"event":"auth","data":{"token":"…"}}` con timeout
  `CHAT_AUTH_TIMEOUT_SECONDS` (5 s), útil para clientes que no quieren el token
  en la URL.
- `thread_id` se acepta como alias de `session_id`; si se envían ambos deben
  coincidir. La sesión debe existir y pertenecer al usuario (4404/4403).
- `manager`/`admin` pueden observar cualquier sesión en **solo lectura**; los
  comandos de escritura solo los acepta el propietario.
- El token en query string queda en logs de acceso; en producción debe usarse
  `wss` y redactar `token` en el proxy. La alternativa por primer frame ya está
  soportada.

## 5. Streaming token a token

`run_agent` acepta `token_sink`, `abort`, `run_id`, `thread_id` y
`conversation_history`. Con `token_sink` usa:

```python
compiled.stream(initial_state, config=config, stream_mode=["updates", "custom"])
```

El nodo `generate` obtiene `get_stream_writer()` y lo pasa como `on_token` al
generador. La generación con memoria pide un JSON con `respuesta` y
`propuesta_memoria`; `AnswerStreamExtractor` emite **solo el valor de
`respuesta`** aunque los deltas lleguen partidos, con escapes o unicode. Así no
se filtra el JSON interno ni la propuesta de memoria.

Las rutas deterministas (tool, sin contexto, guardrails de entrada) no llaman
al LLM: el productor emite el texto final en trozos al cerrar el turno, con el
mismo contrato `token_chunk`.

## 6. Aborto del stream (no es HITL `interrupt()`)

- `abort` es un `threading.Event` enlazado por `ContextVar` a la corrida.
- `chat_json_stream` lo comprueba antes de cada chunk y cierra la respuesta
  HTTP del proveedor; el runner devuelve `status="interrupted"` y escribe la
  traza.
- La generación activa tiene un `emit_lock`: emitir token, publicar
  `interrupt_requested` y cerrar compiten por el mismo lock. Orden garantizado:

```text
token_chunk* → interrupt_requested → generation_interrupted
```

- Tras la interrupción:
  - el mensaje parcial se persiste con `status="interrupted"` y **no se
    sobrescribe** (el store rechaza finalizar dos veces o cambiar un mensaje ya
    cerrado);
  - la sesión pasa a `interrupted`;
  - si `new_input` no está vacío, se persiste el mensaje del usuario, se crea
    un **mensaje asistente nuevo** (`message_id` y `run_id` nuevos) y se lanza
    un turno nuevo sobre el mismo `thread_id`.
- **No se usa `interrupt()` de LangGraph** para esto: `interrupt()` pausa el
  grafo en un checkpoint y espera una reanudación; aquí cancelamos la
  generación y empezamos otro turno. `interrupt()` queda disponible para una
  futura pausa HITL que no sea un abort.

Detalle importante: **una caída de red no aborta**. Solo `interrupt_requested`
(explícito) detiene el stream. La generación sigue y el cliente rehidrata al
reconectar. Es lo que permite “no perder el hilo”.

## 7. Pub/sub y múltiples clientes

- Canal lógico `chat.<session_id>`; `ChatEventBus.subscribe/publish`.
- Varias conexiones de la misma sesión reciben los mismos eventos copiados;
  solo hay **una** llamada al agente por turno, garantizada por
  `GenerationRegistry.try_register`.
- Si un supervisor se conecta (rol manager/admin), recibe el stream pero no
  puede enviar `user_message` ni interrumpir.
- La implementación es en memoria (un proceso), como permite el BRIEFING. La
  interfaz (`subscribe`, `publish`, canal `chat.<session_id>`) es sustituible
  por Redis pub/sub sin cambiar al productor ni al endpoint.
- Cola sin descarte por conexión: una generación está acotada (~1.100 tokens),
  así que no se pierden tokens. Un cliente desconectado vuelve por snapshot.

## 8. Reconexión y rehidratación

1. El cliente reconecta con **el mismo `session_id`/`thread_id`**.
2. El servidor se suscribe primero al canal y luego envía
   `session_snapshot` con los últimos `CHAT_HISTORY_LIMIT` mensajes y, si hay
   una generación en curso, `active_generation` con `sequence` y parcial.
3. El cliente hidrata antes de aceptar tokens nuevos y deduplica por
   `(message_id, sequence)`.
4. Backoff 1→2→4→8→16→30 s con jitter; sin reintento con 4401/4403/4404.
   Watchdog de inactividad 45 s (tres keep-alives perdidos).
5. Al arrancar la API, cualquier mensaje `streaming` huérfano se reconcilia a
   `interrupted`.
6. `thread_id = session_id` mantiene el hilo del checkpointer de LangGraph; el
   historial persistido es la fuente autoritativa para reconstruir la UI y el
   contexto del prompt.

## 9. Preguntas de diseño

### ¿Por qué WebSocket y no SSE?

La Parte 1 era unidireccional (servidor→cliente) y le bastaba SSE sobre HTTP con
el JWT en cabecera. Aquí el requisito exige que el cliente **actúe mientras se
genera**: interrumpir y enviar una nueva entrada para redirigir. Eso es un canal
bidireccional de baja latencia; con SSE habría que abrir un `POST` paralelo que
compite con el stream y no comparte orden de eventos. WebSocket permite
comando y eventos en la misma conexión ordenada.

### ¿Varios clientes en la misma sesión?

Un canal pub/sub por sesión (`chat.<session_id>`) y un único productor por
sesión (`GenerationRegistry`). El primer `user_message` arranca la generación;
las demás conexiones solo consumen. Todos reciben los mismos eventos en el mismo
orden. `session_snapshot` + dedupe por `(message_id, sequence)` evita duplicados
tras una reconexión. Los supervisores entran en solo lectura por rol.

### ¿Abort del stream vs `interrupt()` de LangGraph?

Son mecanismos distintos. El abort es cooperativo y no reanudable: detiene el
stream del modelo, cierra la respuesta HTTP, conserva el parcial como
`interrupted` y arranca un turno nuevo. `interrupt()` pausa el grafo y preserva
un checkpoint esperando `resume`; usarlo aquí mezclaría una pausa de grafo con
una cancelación de UI. El mensaje interrumpido no se toca y la siguiente
respuesta es otro `message_id`/`run_id`.

## 10. Configuración

| Variable | Default | Uso |
|---|---|---|
| `CHAT_HISTORY_LIMIT` | 50 | Mensajes del snapshot. |
| `CHAT_PROMPT_HISTORY_MESSAGES` | 6 | Turnos previos en el prompt. |
| `CHAT_PROMPT_HISTORY_CHARS` | 3000 | Tope de caracteres del historial. |
| `CHAT_MAX_MESSAGE_CHARS` | 4000 | Longitud máxima de un mensaje. |
| `CHAT_AUTH_TIMEOUT_SECONDS` | 5 | Espera del primer frame `auth`. |
| `CHAT_KEEPALIVE_SECONDS` | 20 | Evento `ping` del servidor. |
| `CHAT_ABORT_WAIT_SECONDS` | 10 | Espera del cierre tras abortar. |
| `CHAT_PARTIAL_PERSIST_EVERY` | 20 | Frecuencia de persistencia del parcial. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base para derivar `ws(s)://…/chat/ws`; si falta, en `localhost` se usa ese mismo API y en otros entornos el mismo origen. |

Los `.env*` son archivos protegidos y no se han modificado; los defaults
cubren el desarrollo local.

## 11. Limitaciones conocidas

- Bus en memoria: válido para un proceso. Con varias réplicas de API hace falta
  Redis pub/sub (`chat.<session_id>`) o sticky sessions.
- El token en query string puede aparecer en logs; usar `wss` y redactarlo.
- Durante el streaming los tokens se muestran antes de `validate_output`; si el
  guard bloquea, el evento `generation_completed` lleva `blocked=true` y la UI
  sustituye el parcial por el mensaje seguro.
- La granularidad real del “token” es la del proveedor (deltas de ~10–20
  caracteres), no carácter a carácter.
