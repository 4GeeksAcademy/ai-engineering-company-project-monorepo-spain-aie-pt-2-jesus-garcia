# Trace de ejemplo — corrida `sla-standard`

Export completo en JSON: [`tests/pipelines/fixtures/agent_traces/sla-standard.json`](../../tests/pipelines/fixtures/agent_traces/sla-standard.json)

## Resumen

| Campo | Valor |
|---|---|
| `run_id` | `sla-standard` |
| Pregunta | ¿Cuál es el SLA de un envío estándar dentro del mismo país? |
| Estado | `ok` |
| Nodos ejecutados | `receive_question → retrieve → generate` |
| Duración | 8164.97 ms |
| Inicio | 2026-11-13T16:18:46.203+00:00 |
| Fin | 2026-11-13T16:18:54.368+00:00 |

## Eventos por nodo

| # | Nodo | Siguiente | Checkpoint | Salida (resumen) |
|---|---|---|---|---|
| 0 | `receive_question` | `retrieve` | `1f1df7de…` | status=ok |
| 1 | `retrieve` | `generate` | `1f1df7de…` | context_count=4 |
| 2 | `generate` | `END` | `1f1df7de…` | status=ok, answer_chars=151 |

## Fuentes recuperadas

| Documento | Sección | Chunk | Extracto |
|---|---|---|---|
| `sla-delivery` | SLA de Entrega | 1 | El SLA comprometido contractualmente es un 90% de entregas a tiempo por mes, medido por país. Si un país cae p… |
| `sla-delivery` | SLA de Entrega | 0 | TrackFlow gestiona la última milla en Estados Unidos (Los Ángeles) y España (Zaragoza). Los compromisos de ent… |
| `sla-delivery` | SLA de Entrega | 2 | TrackFlow no garantiza SLA de entrega los días de alta demanda declarados (Black Friday, Navidad, Rebajas de e… |
| `carrier-coverage` | Cobertura de Transportistas | 0 | TrackFlow trabaja con transportistas distintos según el país:  Estados Unidos (Los Ángeles): UPS, FedEx y DHL.… |

## Respuesta final

```text
Según el documento [2] "sla-delivery", sección SLA de Entrega, el compromiso para un envío estándar dentro del mismo país es de **3 a 5 días hábiles**.
```

## Checkpoints serializados

- Paso 0: `next=['retrieve']` | `status=ok` | `answer_chars=0`
- Paso 1: `next=['generate']` | `status=ok` | `answer_chars=0`
- Paso 2: `next=[]` | `status=ok` | `answer_chars=151`
