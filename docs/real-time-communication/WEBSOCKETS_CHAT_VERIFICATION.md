# Verificación — Chat en tiempo real por WebSocket

Complementa el diseño en [`WEBSOCKETS_CHAT_DESIGN.md`](./WEBSOCKETS_CHAT_DESIGN.md)
y los tests automáticos.

## Tests automáticos

```bash
# Backend
cd services/api
./venv/bin/python -m pytest tests/test_chat_streaming.py \
  tests/test_chat_store.py tests/test_chat_events.py \
  tests/test_chat_bus.py tests/test_chat_ws.py -q

# Frontend
cd uis/backoffice
npx vitest run lib/__tests__/chat-types.test.ts \
  lib/__tests__/chat-socket.test.ts "app/(protected)/chat/page.test.tsx"
```

Cobertura:

| Suite | Qué demuestra |
|---|---|
| `test_chat_streaming.py` | Extractor JSON incremental, SSE, aborto sin más tokens y `stream_mode="custom"` de LangGraph con aborto. |
| `test_chat_store.py` | Sesiones/ownership, parcial `interrupted` inmutable, snapshot e historial, reconciliación de huérfanos. |
| `test_chat_events.py` | Contrato nombrado (`token_chunk`, `interrupt_requested`, `generation_interrupted`, `generation_completed`, `session_snapshot`, `user_message`) y orden de cierre. |
| `test_chat_bus.py` | Canales aislados por sesión, fan-out a N suscriptores y publicación desde otro hilo. |
| `test_chat_ws.py` | Rechazo sin JWT, streaming, interrupción medible, turno nuevo y reconexión con snapshot. |
| Vitest | Reducer append-only, backoff del socket, UI token a token, badge de interrumpido y respuesta redirigida. |

## Verificación E2E con el stack real

```bash
docker compose up --build -d services uis qdrant redis
services/api/venv/bin/python scripts/chat_ws_smoke.py
```

El script hace login (admin), crea una sesión y ejecuta los cuatro escenarios.
Salida real de la última ejecución:

```text
session_id=chat_88fe7d7db1
ok snapshot inicial
token seq=1…
ok interrupción: mensaje=msg_45884d8727 parcial='Según nuestros SLA,'
ok turno nuevo: mensaje=msg_c560aa350b texto='Entiendo que desea realizar una devolución. Para ayudarle, necesito el número de'
ok historial: parcial inmutable + turno nuevo persistido
ok reconexión: 4 mensajes restaurados
OK chat WebSocket E2E
```

## Escenarios manuales en el backoffice

Preparación: stack Docker arriba y login en `http://localhost:3001`
(`admin@trackflow.com` / `admin123`). Abre **Chat de soporte** en el sidebar.

### A — Streaming en vivo

1. Envía «¿Cuánto tarda una entrega estándar en España?».
2. La burbuja del agente aparece con cursor `▍` y el texto crece con cada
   `token_chunk`; no llega una única respuesta completa.
3. En DevTools → Network → WS → Messages se ven los frames
   `generation_started`, `token_chunk` con `sequence` creciente y
   `generation_completed`.

### B — Interrupción y redirección

1. Envía «rastrea mi pedido».
2. Mientras responde, escribe «espera, quiero hacer una devolución» y pulsa
   **Interrumpir y enviar**.
3. Se observa:
   - `interrupt_requested` con el `message_id` en curso y `new_input`;
   - `generation_interrupted` con `status="interrupted"` y el texto parcial;
   - **ningún** `token_chunk` de ese `message_id` después del cierre;
   - el parcial queda visible con el badge **Interrumpido**;
   - `user_message` del nuevo texto y un `generation_started` con **otro**
     `message_id`;
   - `generation_completed` del turno nuevo con la respuesta redirigida.
4. El botón **Detener** hace lo mismo sin iniciar un turno nuevo.

Prueba de persistencia:

```bash
curl -s "http://localhost:8000/chat/sessions/<session_id>/messages" \
  -H "Authorization: Bearer <token>" | python -m json.tool
```

El asistente interrumpido conserva `status: "interrupted"` y su `text`; el
siguiente asistente es otra fila con `status: "completed"`.

### C — Caída y reconexión

1. Con una conversación en curso, DevTools → Network → **Offline** (o
   `docker compose stop services`).
2. El pill pasa a **Reconectando…** con intentos 1 s, 2 s, 4 s… sin tormenta
   de peticiones.
3. Restaura la red. El socket reconecta con el mismo `session_id`; el primer
   frame es `session_snapshot` con el historial y, si seguía generando,
   `active_generation` con el parcial.
4. La conversación no aparece vacía y los tokens nuevos continúan sin
   duplicarse (dedupe por `message_id` + `sequence`).

También se puede cerrar la pestaña y volver a abrirla: la sesión se recupera de
`?session=` o de `localStorage`.

### D — Autenticación y sesión

```bash
# Sin token: rechazo antes de cualquier evento
services/api/venv/bin/python - <<'PY'
from websockets.sync.client import connect
try:
    with connect("ws://localhost:8000/chat/ws?session_id=chat_x") as ws:
        print(ws.recv())
except Exception as exc:
    print("rechazado:", type(exc).__name__)
PY
```

- Token inválido → rechazo (HTTP 403 / cierre 4401).
- `session_id` inexistente → cierre 4404.
- Sesión de otro usuario → cierre 4403.
- `manager/admin` puede observar una sesión ajena, pero sus `user_message` e
  `interrupt_requested` reciben `error` y no se ejecutan.

## Qué mirar en los logs

- `services`: `token_chunk` publicados y `generation_interrupted` con el
  `message_id` abortado.
- `uis`: frames WS en orden; ninguna respuesta completa antes del último token.
- `chat_messages`: el parcial interrumpido no cambia tras el turno nuevo.
