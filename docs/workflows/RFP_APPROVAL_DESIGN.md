# Aprobación humana y cierre del documento — Diseño (Hito 9, Parte 3)

La Parte 3 consume el handoff `rfp-proposal-v1` de la Parte 2 y el handoff
`rfp-intake-v1` de la Parte 1. No reparsea el PDF ni vuelve a generar la
propuesta completa: pausa cada departamento con `interrupt`, persiste el estado
con un checkpointer y reanuda con `Command(resume=...)`.

## 1. Piezas

| Pieza | Ubicación |
| --- | --- |
| Contratos y validación | `data/pipelines/rfp_approval/contracts.py` |
| Detección y arbitraje | `data/pipelines/rfp_approval/conflicts.py` |
| Grafo de arbitraje | `data/pipelines/rfp_approval/arbitration_graph.py` |
| Grafo de una rama | `data/pipelines/rfp_approval/approval_graph.py` |
| Grafo de cierre | `data/pipelines/rfp_approval/finalize_graph.py` |
| Documento final | `data/pipelines/rfp_approval/final_document.py` |
| Traza por nodo | `data/pipelines/rfp_approval/trace.py` |
| Runner | `data/pipelines/rfp_approval/runner.py` |
| Persistencia SQL | `services/api/app/services/rfp_approval_service.py` |
| Tareas Celery | `services/api/app/tasks/rfp_approval.py` |
| HTTP | `services/api/app/routes/rfp.py` |
| UI | `uis/backoffice/app/(protected)/rfp/[ticketId]/` |
| Migración | `services/api/migrations/0008_rfp_approval.sql` |

## 2. Flujo

```text
start_approval_flow(ticket)
  → arbitration_graph
        load_proposal → detect_conflicts
          ├─ sin conflictos → END
          ├─ conflictos y rondas < límite → arbitrate → detect_conflicts
          └─ conflictos y rondas = límite → reject_unresolved
  → por cada sección activa:
        build_approval_branch_graph(checkpointer)
          prepare_approval
            → await_approval (interrupt)
            → approve | reject | request_changes
                request_changes → regenerate_section (solo ese depto)
                                  → prepare_approval → await_approval
  → si todas aprobadas: finalize_graph
        load_approvals → final_gate → generate_document → complete
  → si alguna rechazada: ticket needs_human_review, sin documento
```

Cada rama usa su propio hilo:

```text
rfp-{ticket_id}:run-{n}                  # run de aprobación (auditoría)
rfp-{ticket_id}:run-{n}:{department}     # checkpoint de la rama
```

Tickets concurrentes no comparten checkpoint. `run-{n}` se incrementa solo al
iniciar una ejecución nueva (por ejemplo, tras regenerar la propuesta), de modo
que un checkpoint antiguo no contamina la ejecución siguiente.

## 3. Checkpointer y reanudación

- `SqliteSaver` (`langgraph-checkpoint-sqlite`) sobre
  `RFP_APPROVAL_CHECKPOINT_DB` (por defecto
  `data/runtime/rfp-approval/checkpoints.db`). API y worker comparten el volumen
  `./data`; el worker usa `--concurrency=1`.
- En tests se puede usar `RFP_APPROVAL_CHECKPOINT_BACKEND=memory` o inyectar un
  `InMemorySaver`.
- `start_approval_flow` crea las secciones, ejecuta el arbitraje y lanza cada
  rama; cada `interrupt` deja el checkpoint persistido.
- `resume_approval`:
  1. carga el ticket y la sección,
  2. exige `status=esperando_aprobación` y
     `approval_status=pending_approval`,
  3. compara `interrupt_id` con el pendiente persistido,
  4. valida la decisión (Pydantic + reglas de negocio),
  5. invoca `Command(resume={interrupt_id: decision})` sobre el mismo hilo.
- No se vuelve a ejecutar `load_proposal` ni las ramas ya cerradas. El test
  `test_resume_uses_persisted_checkpoint_without_restart` abre una instancia
  nueva del grafo sobre el mismo fichero y comprueba que `load_proposal` aparece
  una sola vez.

## 4. Paquete de aprobación

Cada `interrupt` entrega al humano el mínimo necesario para decidir:

- cliente, país, moneda, servicios y deadline,
- markdown de la sección,
- tabla de tarifas, SLA, descuentos, capacidad/carriers/turnaround,
- resultado de legibilidad, pertinencia y cumplimiento (con `rule_id`),
- supuestos, preguntas abiertas y conflictos que afectan a la sección,
- ronda actual, límite y acciones permitidas,
- responsable nombrado y requisitos de la decisión.

La UI lo muestra en `ApprovalPanel`; la API lo expone en
`GET /rfp/tickets/{id}/approvals`.

## 5. Validación de la decisión

```json
{
  "action": "approve | reject | request_changes",
  "approver": "Ana Whitfield",
  "comment": "...",
  "interrupt_id": "...",
  "acknowledge_provisional": false
}
```

- `approver` debe ser el responsable del catálogo del departamento.
- `reject` y `request_changes` exigen comentario.
- Una sección `provisional` exige `acknowledge_provisional=true` y comentario
  para aprobar.
- `interrupt_id` debe coincidir con el pendiente; una decisión duplicada,
  obsoleta o de otro departamento devuelve 409/422 sin tocar el grafo.
- La validación se hace en el servicio **antes** de encolar y se repite dentro
  del nodo `await_approval`.

## 6. Rechazo y solicitud de cambios

- **`request_changes`**: la rama pausada regenera **solo esa sección**
  reutilizando `build_section_graph` de la Parte 2 con el comentario humano como
  feedback. Guarda el nuevo borrador/evaluación y vuelve a interrumpir en el
  mismo hilo. Los demás departamentos conservan su estado y sus aprobaciones.
- **`reject`**: la sección queda `rejected`, el ticket pasa a
  `needs_human_review` y no se genera documento final. Para reintentar hay que
  regenerar la propuesta (nueva ejecución de la Parte 2 y `run-{n+1}`); el flujo
  no se reinicia desde la Parte 1. Al regenerar, la Parte 2 limpia
  `approval_status`, `approval_interrupt_id` y el paquete anterior: las
  aprobaciones de la ejecución previa no se reutilizan.

## 7. Triggers y árbitro fijo (BRIEFING §7)

| `trigger_id` | Señal estructurada | Árbitro fijo | Resolución |
| --- | --- | --- | --- |
| `volume-vs-capacity` | `lastmile` asume más pedidos/mes que la `max_monthly_orders` declarada por `warehouse` | Miguel Torres | Limitar el volumen a la capacidad de warehouse; Last Mile revisa coste a la baja |
| `returns-sla-breach` | `turnaround` < 48 h o violación `BRIEFING-5.3-RETURNS-48H` | Sofía Ramos; Miguel Torres si otro depto embebe la promesa | `request_changes` en toda sección ofensora; sin documento hasta cumplir |
| `currency-mismatch` | `draft_payload.currency`/tarifas distintas de US→USD, Spain→EUR, o violación `BRIEFING-5.1-CURRENCY` | Miguel Torres | Reescribir a la moneda del país; rechazar si no se resuelve tras el límite |

- La detección usa `draft_payload` y `evaluate_compliance` (motor determinista),
  no texto libre ni votación de LLMs.
- El nodo `arbitrate` registra `rfp_arbitration` y eventos de traza con el
  árbitro nombrado.
- Si tras `RFP_APPROVAL_MAX_ROUNDS` el conflicto persiste, `reject_unresolved`
  rechaza las secciones afectadas y no se genera documento.

## 8. Límites

- `RFP_PROPOSAL_MAX_ITERATIONS` (Parte 2): ciclo generador-evaluador por sección.
- `RFP_APPROVAL_MAX_ROUNDS` (Parte 3, por defecto 2): rondas de arbitraje y
  revisiones humanas. Al alcanzarlo, la sección solo admite `approve` o
  `reject`; el paquete lo refleja en `allowed_actions`.
- El límite es verificable en `approval_round` y en la traza
  (`regenerate_section` con `max_rounds_reached`, `reject_unresolved`).

## 9. Trazabilidad

- `rfp_node_trace` guarda, por ejecución de nodo:
  `ticket_id`, `event_id`, `thread_id`, `part`, `sequence`, `node`, `agent`,
  `department_id`, `input`, `output`, `occurred_at`, `duration_ms`.
- La Parte 3 registra agentes como `approval_orchestrator`, `conflict_detector`,
  `arbitrator:Miguel Torres`, `generator:warehouse`,
  `human:Ana Whitfield` y `document_synthesizer`.
- `GET /rfp/tickets/{id}/trace` fusiona los eventos de la Parte 1 y la Parte 2
  (trazas JSON) con la Parte 3 (SQL), ordenados por parte y secuencia.
- La UI los muestra en `TraceTimeline` con input/output desplegables.

## 10. Documento final

- Solo se genera si todas las secciones activas están `approved` y el
  `final_gate` vuelve a validar §5 (moneda, SLA 90%, ≥48 h, descuentos, sin
  tarifas de transportistas).
- Contrato `rfp-final-v1`; se persiste en `rfp_final_document` y en
  `data/raw/rfp/{ticket_id}/propuesta-final.md`.
- Incluye cabecera, tabla de aprobaciones, secciones consolidadas (con
  encabezados demotados), condiciones comunes, descuentos y preguntas abiertas.
- El ticket pasa a `terminado` y `approval_status=completed`.

## 11. Estados del ticket

```text
analizando → analisis_completo → generando_borrador → en_evaluación
  → esperando_aprobación → terminado
                ↕
         needs_human_review (rechazo o límite agotado)
```

`esperando_aprobación` mientras haya alguna aprobación pendiente;
`terminado` cuando el documento final está guardado y accesible.

## 12. API

| Método | Ruta | Uso |
| --- | --- | --- |
| `POST` | `/rfp/tickets/{id}/approvals/start` | Inicia/reintenta el flujo (202) |
| `GET` | `/rfp/tickets/{id}/approvals` | Pendientes, decisiones, thread y run |
| `POST` | `/rfp/tickets/{id}/approvals/{department}` | Envía la decisión y reanuda la rama (202) |
| `GET` | `/rfp/tickets/{id}/final-document` | Documento final `rfp-final-v1` |
| `GET` | `/rfp/tickets/{id}/final-document/download` | Descarga Markdown |
| `GET` | `/rfp/tickets/{id}/trace` | Timeline completo Partes 1–3 |

## 13. Pruebas

```bash
uv run pytest \
  tests/pipelines/test_rfp_approval_graph.py \
  tests/pipelines/test_rfp_approval_validation.py \
  tests/pipelines/test_rfp_arbitration.py \
  tests/pipelines/test_rfp_approval_limits.py \
  tests/pipelines/test_rfp_approval_trace.py \
  tests/pipelines/test_rfp_e2e.py -q

cd services/api && ./venv/bin/python -m pytest tests/test_rfp_approval_api.py -q
cd uis/backoffice && npm test && npm run lint && npm run build
```

E2E reproducible:

```bash
# Sin red: fixture de la Parte 1 + LLM guionizado en Partes 2 y 3
services/api/venv/bin/python scripts/rfp_e2e.py

# Con LLM real sobre el PDF de la Parte 1
services/api/venv/bin/python scripts/rfp_e2e.py --live \
  --pdf docs/workflows/rfp-requests/trackflow-request-1.pdf --keep
```
