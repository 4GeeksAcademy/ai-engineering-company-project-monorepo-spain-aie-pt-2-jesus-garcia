# Notificaciones en tiempo real (SSE) — Diseño

Implementación de la Parte 1 del briefing de tiempo real: notificar la llegada
de un ticket de RFP (`rfp_ticket_created`) y la alerta de umbral de negocio
(`sla_threshold_alert`) sin recargar el dashboard.

## 1. Arquitectura

```
Celery worker ──publish──▶ Redis pub/sub ──▶ API (una suscripción por proceso)
                                              │
                                              ├─ fan-out ▶ conexión SSE de cada pestaña
                                              └─ replay corto (Last-Event-ID)
```

- **Una conexión por cliente, independiente.** Cada pestaña/usuario abre su
  propio `GET /realtime/stream`; cerrar una no afecta a las demás.
- **Infraestructura compartida:** el bus es un singleton por proceso
  (`app/realtime/broker.py`). En Docker es Redis pub/sub porque el pipeline de
  RFPs corre en un worker Celery aparte; sin Redis el evento nacería en un
  proceso que la API no escucha. En tests y desarrollo de un solo proceso se
  usa `LocalBroker` (misma interfaz).
- **Fan-out O(n) en memoria:** el evento se publica una vez y se copia a la
  cola acotada de cada conexión. La base de datos no se consulta por evento;
  se lee un snapshot al conectar.
- **Backpressure explícito:** si una cola se llena se descarta el evento más
  antiguo y se emite `stream_lagged` para que ese cliente reconcilie con el
  snapshot. Un cliente lento nunca bloquea al resto.
- **50 conexiones simultáneas:** 50 colas en el proceso de la API y una sola
  suscripción a Redis; el coste por evento es un `put_nowait` por conexión.
  Para más carga se añaden réplicas de API: todas se suscriben a Redis y no
  comparten estado mutable. El límite práctico es el de conexiones HTTP/1.1
  por origen del navegador (6); en producción se sirve por HTTP/2 o dominio
  dedicado.

## 2. Contrato de eventos

El nombre viaja en la línea `event:` y `data:` lleva **solo campos de la
entidad**, sin sobre `{"event","data"}`.

`rfp_ticket_created` — al registrar el ticket (`POST /rfp/tickets`,
`status=analizando`):

```text
event: rfp_ticket_created
data: {"ticket_id":"…","rfp_id":"RFP-20261115-A1B2C3","client_name":null,
       "client_country":null,"services_requested":[],"currency":null,
       "status":"analizando","created_at":"2026-11-15T14:32:00Z",
       "original_filename":"trackflow-request-1.pdf","pipeline_stage":"encolado"}
```

En el instante del registro los metadatos de la RFP aún no existen (los extrae
el pipeline). Cuando el clasificador confirma que es una RFP válida y guarda
los metadatos, el worker emite `rfp_ticket_metadata_ready` con el **mismo**
`ticket_id` y los campos ya rellenos (`client_name`, `client_country`,
`services_requested`, `currency`). El dashboard actualiza la tarjeta en lugar
de duplicarla.

`sla_threshold_alert` — cuando el SLA de entrega a tiempo cae por debajo del
90 % en US o España:

```text
event: sla_threshold_alert
data: {"alert_id":"sla:2026-11-09:US","metric":"on_time_delivery_pct",
       "country":"US","warehouse":"los_angeles","week_start":"2026-11-09",
       "threshold_pct":90.0,"on_time_pct":88.4,"total_shipments":1520,
       "on_time_shipments":1344,"breached":true,
       "recipients":[{"name":"Thomas Harry","role":"CEO"},
                     {"name":"Ana Whitfield","role":"Warehouse Operations"}],
       "detected_at":"2026-11-16T09:00:00Z"}
```

`stream_lagged` — aviso interno de cola descartada (`{"dropped": n}`), sin
`id:`; el cliente lo trata como orden de reconciliación.

## 3. Autenticación y transporte

- El stream está protegido con `require_manager`, el **mismo JWT** que el resto
  del backoffice. Sin token o con token inválido la respuesta no es
  `text/event-stream` y no se entrega ningún evento.
- El cliente usa `fetch` + `ReadableStream` (no `EventSource`) porque
  `EventSource` no permite enviar `Authorization` de forma limpia.
- Cabeceras: `Content-Type: text/event-stream`, `Cache-Control: no-cache,
  no-transform`, `X-Accel-Buffering: no`, `Connection: keep-alive`.
- Keep-alive por comentario SSE (`: keep-alive`) cada `SSE_KEEPALIVE_SECONDS`
  (15 s por defecto) para que proxies y balanceadores no cierren la conexión.
- Preámbulo `retry: 3000` como pista estándar; el backoff real lo aplica el
  cliente.

## 4. Recuperación tras una caída (estrategia elegida)

**Snapshot-after-stream + dedupe por `ticket_id`, con `Last-Event-ID` como
segunda capa.** No hay pérdidas silenciosas:

1. Al montar y en **cada** reconexión, el cliente abre el stream primero y
   luego pide el snapshot `GET /rfp/tickets`. Así ningún evento puede caer
   entre la lectura del snapshot y la suscripción.
2. Mientras el snapshot está en vuelo, los eventos recibidos se acumulan en el
   `Map<ticket_id, ticket>`: el snapshot es autoritativo y el `Map` deduplica.
3. El servidor asigna `id:` monotónico y guarda un buffer corto (Redis:
   `realtime:events:recent`, últimos `REALTIME_REPLAY_LIMIT`, 1 h). El cliente
   reenvía `Last-Event-ID` y recibe esos eventos antes de los nuevos.
4. Si una cola desbordó, `stream_lagged` fuerza la reconciliación por snapshot.
5. Tras una reconexión, un `ticket_id` que aparece en el snapshot y no estaba
   en el estado previo se notifica **una vez** como “Recuperado”
   (`notifiedRef` evita repetirlo). La tabla se renderiza con una clave por
   `ticket_id`: nunca hay dos filas para el mismo ticket.

El backoff es 1 s → 2 s → 4 s → 8 s → 16 s → 30 s (tope) con jitter ±20 %; se
reinicia al abrir el stream y no se reintenta ante 401/403. Un watchdog de
inactividad (45 s = tres keep-alives perdidos) corta las conexiones "mudas"
—por ejemplo un proxy que no propaga el cierre del upstream— y entra en el
mismo backoff.

## 5. Preguntas de diseño

### ¿Cada conexión SSE independiente o una capa intermedia compartida?

Independiente por cliente y **compartida** en infraestructura: cada conexión
tiene su cola y su ciclo de vida, pero todas consumen del mismo bus. Con 50
personas hay 50 colas en la API y una suscripción a Redis por réplica; el
evento se publica una vez y se copia n veces. No hay polling por usuario ni
una consulta a base de datos por evento.

### ¿Qué estrategia de recuperación y cómo se evitan duplicados?

La de §4: snapshot después de adjuntar el stream + `Map` por `ticket_id` +
`Last-Event-ID`. Los duplicados se evitan en tres niveles: evento repetido →
mismo `ticket_id` actualiza la tarjeta; snapshot + evento → el `Map` colapsa
ambos; aviso repetido → `notifiedRef` lo silencia.

### ¿Por qué SSE y no WebSockets?

El flujo es unidireccional servidor→cliente. SSE viaja sobre HTTP normal, así
que reutiliza el JWT `Bearer` del backoffice, el CORS y los proxies existentes,
sin `Upgrade` ni protocolo propio, y trae reconexión/replay por diseño.
Dejaría de ser la herramienta correcta si el mismo canal necesitara interacción
cliente→servidor en tiempo real (aprobar/rechazar o comentar el ticket desde el
mismo stream), presencia/colaboración o tráfico bidireccional intenso. Para
comandos puntuales, SSE (servidor→cliente) + `POST` HTTP sigue siendo válido;
para bidireccional continuo, WebSocket.

## 6. Alerta de umbral de negocio

El pipeline semanal de desempeño mide almacén (inbound/outbound/stockout/
discrepancia), no entregas. Para no inventar el umbral, la regla del briefing
se implementa sobre un read model explícito:
`reporting.delivery_sla_weekly` (semana, país, almacén, envíos totales / a tiempo).
El feed real de última milla lo poblará cuando exista; para la demo se siembra
una semana reproducible:

```bash
python scripts/seed_delivery_sla.py --force
```

- `GET /reporting/sla-status` devuelve el estado y el umbral (90 %).
- `POST /reporting/sla/evaluate` evalúa y emite `sla_threshold_alert` una sola
  vez por `(semana, país)`; el botón “Evaluar umbral SLA” del dashboard lo usa y
  puede programarse por cron.
- El dashboard muestra la alerta en `/reporting` (país, % real, umbral,
  destinatarios) y la actualiza en vivo por SSE.

## 7. Operación

| Variable | Uso |
|---|---|
| `REDIS_URL` | Si está definida (Docker), el bus es Redis pub/sub. |
| `REALTIME_BROKER` | `local` fuerza el bus en memoria (tests); `redis` lo fuerza. |
| `REALTIME_QUEUE_SIZE` | Eventos en cola por conexión (200). |
| `REALTIME_REPLAY_LIMIT` | Tamaño del buffer de replay (200). |
| `SSE_KEEPALIVE_SECONDS` | Frecuencia del comentario keep-alive (15). |

Sin `REDIS_URL` (desarrollo local con la API sola) el bus es local: el evento
de `POST /rfp/tickets` funciona, pero el enriquecimiento emitido por el worker
requiere Redis para cruzar de proceso. Docker Compose ya define `REDIS_URL`
para `services` y `worker`.
