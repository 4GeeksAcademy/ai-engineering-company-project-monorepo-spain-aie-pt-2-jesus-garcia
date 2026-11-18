# Generación y evaluación de propuestas — Diseño (Hito 9, Parte 2)

La Parte 2 arranca del handoff de enrutamiento de la Parte 1 y produce una
sección de propuesta económica por departamento activo, evaluada en paralelo
por legibilidad, pertinencia y cumplimiento, con ciclo de reintento acotado.

## 1. Entrada: handoff de la Parte 1 (sin reparsear el PDF)

- Fuente: `rfp_ticket.handoff_payload` (JSONB) con
  `handoff_status = 'ready'` y `status = 'analisis_completo'`.
- Validación: `data/pipelines/rfp_proposal/contract.py`.
- La Parte 1 añadió `rfp_facts` (`monthly_volume`, `sku_count`,
  `return_volume`, `return_rate`, `deadline`, `budget_range`) al handoff para
  cotizar sin volver a leer el PDF. Si un handoff antiguo no lo trae, la Parte 2
  cae a `rfp_metadata` (misma base de datos).
- `source.pdf_path` solo se conserva para trazabilidad: el pipeline no importa
  el convertidor ni abre el archivo. Hay un test que genera la propuesta con
  rutas inexistentes.

## 2. Layout

| Pieza | Ubicación |
| --- | --- |
| Contrato y política | `data/pipelines/rfp_proposal/{contract,policy,rate_card,render}.py` |
| Generadores | `data/pipelines/rfp_proposal/generators/{base,warehouse,lastmile,reverse}.py` |
| Evaluadores | `data/pipelines/rfp_proposal/evaluators/{result,readability,relevance,compliance}.py` |
| Grafos | `data/pipelines/rfp_proposal/{section_graph,graph}.py` |
| Handoff Parte 3 | `data/pipelines/rfp_proposal/handoff.py` |
| Persistencia SQL | `services/api/app/services/rfp_proposal_service.py` |
| Tarea async | `services/api/app/tasks/rfp_proposal.py` (Celery) |
| HTTP | `services/api/app/routes/rfp.py` (router existente) |
| UI | `uis/backoffice/app/(protected)/rfp/[ticketId]/` |
| Migración | `services/api/migrations/0007_rfp_proposal.sql` |
| Política | `docs/workflows/RFP_PROPOSAL_POLICY.md` |

No hay un segundo servicio HTTP.

## 3. Flujo

```
load_handoff (valida contrato; ticket → generando_borrador)
  → plan (un brief por departments[])
  → Send(department) × N        ← departamentos en paralelo
       generate ──Send──> evaluate_readability ┐
                        > evaluate_relevance    ├─> collect ──> decide
                        > evaluate_compliance   ┘              │
                                                  ├─ pass ───────→ END
                                                  ├─ fail (iter<max) → generate
                                                  └─ fail (iter=max) → exhausted
                                                      (needs_human_review)
  → finalize_proposal (handoff rfp-proposal-v1; estado del ticket)
```

Cada departamento tiene su propio subgrafo generador-evaluador compilado. Un
departamento que agota iteraciones no bloquea al resto.

## 4. Generadores por departamento

| `department_id` | Agente | Aporta (§2.1) |
| --- | --- | --- |
| `warehouse` | `WarehouseGenerator` (Ana Whitfield) | capacidad, coste de almacenamiento, onboarding |
| `lastmile` | `LastMileGenerator` (Carlos Vega) | transportistas por destino, coste por envío, SLA |
| `reverse` | `ReverseGenerator` (Sofía Ramos) | proceso, coste y tiempo de devoluciones (≥ 48 h) |

- El LLM escribe la prosa (`executive_summary`, `offerings`, `assumptions`,
  preguntas). Las **tablas de precio, descuentos y SLA se construyen
  determinísticamente** desde `rate_card.py` y `policy.py`.
- Guardarraíl numérico: cualquier cifra de la prosa que no venga del handoff,
  de la tarifa publicada o de la política se elimina y se convierte en pregunta
  abierta.
- Lo no publicado se marca `pendiente_confirmacion` con el responsable; nunca se
  estima.
- En reintento, el prompt incluye el borrador anterior y el
  `feedback_for_generator` verbatim.

## 5. Evaluadores (paralelos)

| Evaluador | Qué recibe | Cómo decide |
| --- | --- | --- |
| `readability` | solo el Markdown de su sección | Fórmula Fernández-Huerta (español) + longitud de frase/párrafo. `py-readability-metrics` se reporta en `details` cuando está disponible |
| `relevance` | su brief (key_aspects, open_questions, foco, datos) + su borrador | Cobertura determinista de `key_aspects` y conservación de preguntas; juez LLM opcional para huecos semánticos |
| `compliance` | pack de reglas §5 + país/moneda + su borrador + cifras permitidas | Motor de reglas determinista con `rule_id`, cita y cambio exigido |

Ningún evaluador recibe el documento completo, el PDF ni otras secciones.

`EvaluationResult` persistido:

```json
{
  "section_id": "<ticket_id>:warehouse",
  "department_id": "warehouse",
  "iteration": 2,
  "readability": {"pass": true, "score": 58.4, "details": {}},
  "relevance": {"pass": false, "missing_aspects": ["Onboarding"], "details": {}},
  "compliance": {"pass": false, "rule_ids": ["…"], "violations": []},
  "overall_pass": false,
  "feedback_for_generator": "1. [BRIEFING-5.3-RETURNS-48H] …"
}
```

## 6. Ciclo y revisión humana

- Límite por defecto: **2 iteraciones** (`RFP_PROPOSAL_MAX_ITERATIONS`).
- Si una sección agota el límite: se conserva el último borrador y su
  `EvaluationResult`, la sección queda `needs_human_review` (con
  `review_reason`) y **se incluye igualmente** en el handoff a la Parte 3, con
  `provisional: true`.
- El ticket queda `needs_human_review` si alguna sección lo está; si todas
  pasan, `esperando_aprobación` (lista para la aprobación por departamento de la
  Parte 3).

Estados del ticket en la Parte 2: `generando_borrador` → `en_evaluación` →
`esperando_aprobación` | `needs_human_review`. Los estados por sección se
exponen en `rfp_department_section.generation_status`.

## 7. Persistencia

- `rfp_ticket`: `proposal_status`, `proposal_stage`, `proposal_payload`,
  `proposal_ready_at`, `proposal_task_id`, `proposal_error`.
- `rfp_department_section`: `draft_content`, `draft_payload`,
  `evaluation_results`, `generation_status`, `iteration_count`,
  `needs_human_review`, `review_reason`, `last_feedback` (los campos de
  aprobación siguen reservados a la Parte 3).
- `rfp_section_evaluation`: histórico por `(ticket, departamento, iteración)`
  con `overall_pass`, `readability`, `relevance`, `compliance` y `feedback`.

## 8. API (sin servicio nuevo)

| Método | Ruta | Uso |
| --- | --- | --- |
| `POST` | `/rfp/tickets/{id}/proposal` | Encola la generación (202). 409 si el handoff no está listo o ya hay una ejecución activa |
| `GET` | `/rfp/tickets/{id}/proposal` | Borradores, evaluaciones, estados, métricas |
| `GET` | `/rfp/tickets/{id}` | Incluye secciones con borrador/evaluación y `proposal_status` |

`GET /rfp/tickets?status=analisis_completo` sigue siendo la cola de entrada.

## 9. UI (Ventas)

- Botón «Generar propuesta» / «Regenerar propuesta» en el detalle del ticket.
- Polling cada 3 s mientras hay análisis o generación/evaluación en curso.
- Tarjeta por sección con los tres criterios (OK/falla), violaciones con
  `rule_id`, feedback y borrador.
- Banner ámbar «Borrador provisional: requiere revisión humana antes de
  enviarlo al cliente» con el motivo del bloqueo.

## 10. Pruebas

```bash
uv run pytest \
  tests/pipelines/test_rfp_proposal_contract.py \
  tests/pipelines/test_rfp_proposal_generator.py \
  tests/pipelines/test_rfp_proposal_evaluators.py \
  tests/pipelines/test_rfp_proposal_cycle.py \
  tests/pipelines/test_rfp_proposal_graph.py -q

cd services/api && ./venv/bin/python -m pytest tests/test_rfp_proposal_api.py -q
cd uis/backoffice && npm run lint && npm test && npm run build
```

Casos cubiertos: handoff válido de la Parte 1, rechazo de contratos inválidos,
generación sin PDF, tarifas/moneda correctas, cifras inventadas descartadas,
legibilidad pasa/falla, pertinencia con aspectos perdidos, **fallo de
compliance anclado a §5.3 (devoluciones en 24 h)**, fuga de tarifa de
transportista, moneda incorrecta, ausencia de descuentos, SLA distinto de 90 %,
reintento con feedback, agotamiento con `needs_human_review` y handoff
provisional, no bloqueo entre departamentos y persistencia en SQL.

## 11. Decisiones abiertas y supuestos

- **Tramos de descuento**: el briefing exige la tabla pero no la cifra; se
  documentan en `RFP_PROPOSAL_POLICY.md` como política interna pendiente de
  validación de Miguel Torres.
- **Precios no publicados**: se muestran como pendientes; no se estiman.
- **Legibilidad**: `py-readability-metrics` usa `nltk.sent_tokenize`, que
  necesita `punkt_tab`. El Dockerfile lo descarga en el build; si falta, el
  evaluador cae a la fórmula Fernández-Huerta determinista y lo indica en
  `details`.
