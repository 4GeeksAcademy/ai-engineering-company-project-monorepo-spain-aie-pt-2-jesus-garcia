# Verificación manual — reconexión y recuperación SSE

Complementa los tests automáticos:

- `services/api/tests/test_realtime_sse.py` — headers `text/event-stream`,
  framing con `event:` nombrado, JSON de `data`, replay por `Last-Event-ID`,
  JWT obligatorio y publicación al subir un PDF.
- `services/api/tests/test_realtime_broker.py` — fan-out, cola llena y
  publicación desde otro hilo.
- `uis/backoffice/lib/__tests__/sse.test.ts` — backoff 1→2→4…→30 s, `Last-Event-ID`
  en la reconexión y ausencia de reintentos ante 401.
- `uis/backoffice/hooks/__tests__/useRfpRealtime.test.tsx` — dedupe por
  `ticket_id`, enriquecimiento sin duplicar y recuperación de tickets perdidos.

## Preparación

```bash
# 1) Backend + Redis + worker + UI
docker compose up --build -d redis services worker uis

# 2) Semana demo de SLA (una sola vez)
docker compose exec services python scripts/seed_delivery_sla.py --force
# Alternativa local:
# cd services/api && ./venv/bin/python ../../scripts/seed_delivery_sla.py --force

# 3) Login en http://localhost:3001 con un usuario manager/admin
#    (seed: admin@trackflow.com / admin123)
```

> En desarrollo local con `npm run dev` (puerto 3000) el navegador usa el
> rewrite same-origin `/api/realtime/*`. Si el proxy del dev server no propaga
> el cierre del backend, el watchdog de inactividad (45 s) fuerza la
> reconexión. Para saltar el proxy y conectar directo al API, exporta
> `NEXT_PUBLIC_API_URL=http://localhost:8000` antes de `npm run dev` (el origen
> `http://localhost:3000` ya está en CORS).

## Escenario A — llegada en vivo

1. Abre `/rfp` en la pestaña A y en la pestaña B.
2. En A sube `docs/workflows/rfp-requests/trackflow-request-1.pdf` (ModaViva).
3. En B, sin recargar, aparece la tarjeta “Llegada de RFPs en vivo” con el
   chip **Nuevo**, `RFP-…`, estado `Analizando` y la hora. El pill muestra
   “Tiempo real · conectado”.
4. Cuando el pipeline extrae los metadatos, la misma tarjeta se enriquece con
   cliente/país/servicios (evento `rfp_ticket_metadata_ready`); no aparece una
   segunda tarjeta.

## Escenario B — caída, backoff y recuperación

1. En la pestaña B: DevTools → Network → **Offline** (o
   `docker compose stop services`).
2. El pill pasa a “Reconectando (intento 1 en 1 s)…”, luego 2 s, 4 s, 8 s…
   (tope 30 s) sin tormenta de peticiones.
3. **Con B desconectado**, sube otro PDF desde la pestaña A
   (`trackflow-request-2.pdf`, Luna Cosmetics). La petición la atiende el
   backend porque está arriba.
4. Restaura la red (o `docker compose start services`). El backoff dispara la
   reconexión: el snapshot se pide después de adjuntar el stream y el ticket
   perdido aparece **una sola vez**, con chip **Recuperado**.
5. Comprobación de duplicados: la tabla tiene una única fila para ese
   `ticket_id`; recargar la página mantiene una sola notificación por ticket
   (las ya descartadas no reaparecen).

> Para verificar el replay corto: en DevTools → Network, la petición SSE de
> reconexión lleva `Last-Event-ID`; si el ticket se creó dentro de la ventana
> del buffer, llega por replay y, si no, por el snapshot. Ambos caminos
> deduplican por `ticket_id`.

## Escenario C — alerta de umbral de SLA

1. Con la semana demo sembrada, abre `/reporting`.
2. El banner “Umbral de negocio · SLA de entrega” muestra US al 88,4 % (< 90 %)
   y los destinatarios Thomas Harry y Ana Whitfield.
3. Pulsa “Evaluar umbral SLA”: se emite `sla_threshold_alert` y el pill del
   banner pasa a “Alerta en vivo”. Una segunda evaluación no duplica la alerta
   (idempotencia por semana y país).
4. En otra pestaña con `/reporting` abierto, la alerta llega por SSE sin
   recargar.

## Escenario D — sin JWT

```bash
curl -i http://localhost:8000/realtime/stream
# 401/403, sin Content-Type: text/event-stream

curl -i -H "Authorization: Bearer token-invalido" \
  http://localhost:8000/realtime/stream
# 401
```
