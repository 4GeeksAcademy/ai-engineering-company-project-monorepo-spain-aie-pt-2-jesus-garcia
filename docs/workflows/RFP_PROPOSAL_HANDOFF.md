# Contrato de handoff — Parte 2 → Parte 3

La Parte 3 no genera ni reevalúa secciones: recibe los borradores ya evaluados
(aprobados por evaluación o marcados para revisión humana) junto con su
`EvaluationResult` completo.

## Dónde vive

- `rfp_ticket.proposal_payload` (JSONB) con contrato `rfp-proposal-v1`.
- `rfp_ticket.proposal_status` = `esperando_aprobación` | `needs_human_review`.
- `rfp_ticket.proposal_ready_at`.
- `GET /rfp/tickets/{ticket_id}/proposal` (admin/manager).

También se puede reconstruir desde `rfp_department_section` (borrador,
evaluación y estado por sección) y `rfp_section_evaluation` (histórico).

## Forma del payload

```json
{
  "contract_version": "rfp-proposal-v1",
  "ticket_id": "4f4d...",
  "rfp_id": "RFP-20260803-AB12CD",
  "status": "needs_human_review",
  "generated_at": "2026-11-15T12:00:00+00:00",
  "client": {"name": "ModaViva, S.L.", "country": "Spain", "currency": "EUR", "contact": {}},
  "client_country": "Spain",
  "currency": "EUR",
  "services_requested": ["warehousing", "reverse_logistics"],
  "sections": [
    {
      "section_id": "4f4d...:warehouse",
      "department_id": "warehouse",
      "department_label": "Warehouse Operations",
      "responsible": "Ana Whitfield",
      "status": "evaluated_pass",
      "provisional": false,
      "iteration_count": 1,
      "draft_content": "# Propuesta de Almacenamiento — ModaViva, S.L.\n…",
      "draft_payload": {
        "capacity": {"sku_count": 15000, "storage_basis": "m³/mes"},
        "pricing": [{"concept": "Almacenamiento", "unit": "m³/mes", "amount": 16, "currency": "EUR"}],
        "discount_tiers": [{"min_monthly_volume": 0, "max_monthly_volume": 1999, "discount_pct": 0}],
        "sla": {"on_time_pct": 90},
        "assumptions": [],
        "open_questions": ["Falta el volumen mensual de pedidos: confirmarlo."]
      },
      "evaluation_results": {
        "readability": {"pass": true, "score": 68.9, "details": {}},
        "relevance": {"pass": true, "missing_aspects": [], "details": {}},
        "compliance": {"pass": true, "rule_ids": ["BRIEFING-5.1-CURRENCY"], "violations": []},
        "overall_pass": true,
        "feedback_for_generator": ""
      },
      "review_reason": null,
      "approval_status": "pending_approval",
      "approver": null,
      "approved_at": null
    }
  ],
  "needs_human_review_sections": [],
  "metrics": {"sections": 2, "average_iterations": 1.0, "max_iterations_used": 1},
  "source_handoff": {"contract_version": "rfp-intake-v1", "handoff_ready": true}
}
```

## Reglas para la Parte 3

1. Usar `sections[]` como lista cerrada de secciones activas; no añadir
   departamentos ni cambiar `currency`.
2. `overall_pass: true` **no es aprobación humana**: `approval_status` empieza en
   `pending_approval`.
3. Toda sección con `provisional: true` o `approval_status:
   needs_human_review` debe mostrarse como borrador provisional y requerir
   decisión humana explícita; nunca entra en el documento final por sí sola.
4. Los conflictos detectables (`volume-vs-capacity`, `returns-sla-breach`,
   `currency-mismatch`) se arbitran en el nodo dedicado de la Parte 3 a partir
   de `draft_payload` y `evaluation_results`; no hace falta reparsear nada.
5. `draft_content` es el Markdown listo para el documento final;
   `draft_payload` es la fuente estructurada para tablas y validaciones.
6. Las `open_questions` deben viajar al documento/entrega; no se eliminan.
