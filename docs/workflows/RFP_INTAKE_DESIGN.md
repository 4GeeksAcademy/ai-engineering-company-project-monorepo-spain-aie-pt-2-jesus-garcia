# RFP Intake — Diseño (Hito 9, Parte 1)

Recepción de RFPs de TrackFlow: subida por backoffice → PDF a Markdown →
clasificación → metadatos + legibilidad → orchestrator-worker-synthesizer →
handoff para la Parte 2.

## 1. Layout y fronteras

| Pieza | Ubicación |
|---|---|
| Grafo y agentes | `data/pipelines/rfp_intake/` |
| HTTP (router único) | `services/api/app/routes/rfp.py` |
| Persistencia | `services/api/app/services/rfp_service.py` + SQLModel |
| Tarea async | `services/api/app/tasks/rfp_intake.py` (Celery) |
| UI | `uis/backoffice/app/(protected)/rfp/` |
| PDFs de muestra | `docs/workflows/rfp-requests/` |
| Scripts manuales | `scripts/rfp_smoke.py`, `scripts/rfp_reprocess.py` |

No hay un segundo servicio HTTP. El router solo valida, guarda el PDF, crea el
ticket y encola; toda la lógica de agentes vive en `data/pipelines/rfp_intake/`.
El grafo CX (`services/api/app/agent/`) no se toca.

> Nota: `MILESTONE_9.md` menciona `rfp-requests/trackflow/`, pero los PDFs
> entregados están en `docs/workflows/rfp-requests/`. Se usa la ruta real.

## 2. Flujo del grafo `rfp_intake`

```
validate_input
  → convert_pdf (MarkItDown; obligatorio antes de cualquier agente)
  → compute_readability (determinista)
  → classify (agente clasificador)
      ├─ no es RFP → ticket `descartado` (END)
      └─ es RFP → extract_metadata (agente)
                   → orchestrate (agente + allowlist de departamentos)
                       ├─ sin servicios del catálogo → `descartado` (END)
                       └─ workers en paralelo (Send por workstream)
                            → synthesize
                            → ticket `analisis_completo` + handoff
```

Cada nodo persiste su avance en `rfp_ticket.pipeline_stage`: `validando`,
`convirtiendo`, `markdown_listo`, `clasificando`, `clasificado`,
`extrayendo_metadatos`, `metadatos_extraidos`, `orquestando`, `orquestado`,
`analizando_<department>`, `sintetizando`, `completado`, `descartado`.

## 3. Estados del ticket

| Estado | Cuándo |
|---|---|
| `analizando` | Subida aceptada / pipeline en curso |
| `analisis_completo` | Handoff listo (`handoff_status=ready`) |
| `descartado` | No es RFP o no pide servicios del catálogo |
| `error` | Fallo técnico terminal tras reintentos (no es un descarte) |

`error` es explícito para no mentir: un job caído no puede parecer
`analizando` eternamente ni `analisis_completo`. La Parte 1 nunca usa
`esperando_aprobación`.

## 4. Async y verdad del ticket

- `POST /rfp/tickets` guarda el PDF en `data/raw/rfp/{ticket_id}/`, crea la fila
  `analizando` y encola `rfp_intake.process_ticket` en Celery (Redis existente).
- Responde **202** con `ticket_id`, `rfp_id` y `task_id`.
- La UI hace polling cada 3 s de `GET /rfp/tickets/{id}/status`.
- Reintentos Celery con backoff; al agotarlos se registra en
  `dead_letter_tasks` y el ticket queda `error` con `pipeline_stage` y
  `error_message` (nunca un éxito parcial).
- Idempotencia/reproceso: si el Markdown ya existe se reutiliza; metadatos y
  secciones hacen upsert por `(ticket_id, department_id)`.
- `scripts/rfp_reprocess.py --ticket-id ...` reejecuta sin HTTP.

## 5. Persistencia (PostgreSQL/Supabase)

- `rfp_ticket`: estado, rutas, hash, clasificación, error, handoff.
- `rfp_metadata`: cliente, país, moneda, servicios, volumen, deadline,
  presupuesto, `readability_metrics` y `document_metadata`.
- `rfp_department_section`: `key_aspects`, `open_questions`, `assumed_facts`,
  `unsupported_claims` y campos nulos de borrador/evaluación/aprobación para
  las Partes 2 y 3.

DDL: `services/api/migrations/0006_rfp_intake.sql` (idempotente). En tests se
crea con `SQLModel.metadata.create_all` sobre SQLite.

## 6. Metadatos y legibilidad

- El LLM propone; la normalización es determinista: país (`US`/`Spain`),
  moneda (`US→USD`, `Spain→EUR`), volumen (`5,000`/`5.000`), fecha ISO,
  presupuesto literal. Lo que no consta queda `null` y en `missing_fields`.
- Métricas: palabras, frases, Flesch Reading Ease, Flesch-Kincaid, tokens
  estimados (`chars/4`), minutos de lectura, banda de complejidad y coste
  (`bajo`/`medio`/`alto`).
- Se evaluó `py-readability-metrics`, pero depende de descargar datos de NLTK
  en runtime (red/no determinismo en Docker/CI). La implementación propia usa
  las mismas fórmulas y es determinista; el objetivo es anticipar el coste.

## 7. Decisiones de diseño

### ¿Y si la RFP menciona un departamento que no existe?

El catálogo es cerrado: `warehouse`, `lastmile`, `reverse`. El clasificador y
los metadatos normalizan alias (`shipping`→`lastmile`, `returns`→`reverse`,
etc.) y guardan lo desconocido en `unknown_services`. El orquestador **no** crea
un worker para un departamento inexistente; añade una pregunta para Ventas. Si
no queda ningún servicio canónico, el ticket se descarta por “fuera de alcance”.

### ¿Qué recibe cada worker?

Metadatos canónicos + extractos de su departamento (slicing determinista por
keywords/headings), **no** el documento completo. Si falta una cifra necesaria
(volumen, SKUs, devoluciones, destino) se registra en `open_questions`; nunca se
estima. Un guardarraíl numérico descarta cualquier `key_aspect` con cifras que
no aparezcan en los metadatos o extractos y pide confirmación.

### ¿Cómo se decide que un documento no es una RFP?

RFP = petición entrante de una marca/prospecto para contratar servicios
logísticos de TrackFlow (formal o informal). No es RFP: pitch de transportista o
proveedor, marketing, facturas, contratos o documentos internos. Hay un
guardarraíl determinista para pitches de carrier (señales de venta hacia
TrackFlow sin señales de petición). Un falso negativo queda auditable en
`classification` (motivo + confianza), visible en la UI y reprocesable; nunca
desaparece en silencio.

### ¿Dos workers con información contradictoria?

Las secciones son disjuntas (`unique (ticket_id, department_id)`). Los datos
compartidos son canónicos: cada worker devuelve `assumed_facts`, el synthesizer
los compara con los metadatos y, si hay conflicto, gana el metadato canónico y
se registra en `conflicts` + pregunta abierta. La negociación/arbitraje formal
es de la Parte 3.

## 8. Pruebas

```bash
services/api/venv/bin/python -m pytest \
  tests/pipelines/test_rfp_classifier.py \
  tests/pipelines/test_rfp_metadata.py \
  tests/pipelines/test_rfp_worker.py \
  tests/pipelines/test_rfp_orchestrator.py \
  tests/pipelines/test_rfp_graph.py \
  tests/pipelines/test_rfp_readability.py \
  tests/pipelines/test_rfp_ingest.py -q

cd services/api && ./venv/bin/python -m pytest tests/test_rfp_api.py -q
cd uis/backoffice && npm test
```

Casos clave: ModaViva activa `warehouse`+`reverse` y no `lastmile`; Luna activa
`warehouse`+`lastmile` con USD; RapidShip se descarta; worker sin volumen no
inventa y pregunta; cifras inventadas se descartan.
