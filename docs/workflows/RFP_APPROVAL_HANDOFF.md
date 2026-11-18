# Contrato de cierre — Parte 3 (`rfp-final-v1`)

La Parte 3 no reescribe la propuesta: consume `rfp-proposal-v1`, recoge la
aprobación humana de cada departamento activo y, solo entonces, sintetiza el
documento final acordado.

## Dónde vive

- `rfp_final_document` (PostgreSQL/Supabase) con `ticket_id` único.
- `data/raw/rfp/{ticket_id}/propuesta-final.md` (artefacto runtime).
- `GET /rfp/tickets/{ticket_id}/final-document`.
- `GET /rfp/tickets/{ticket_id}/final-document/download`.
- `rfp_ticket.status = 'terminado'` y `approval_status = 'completed'`.

## Forma del payload

```json
{
  "contract_version": "rfp-final-v1",
  "ticket_id": "4f4d...",
  "rfp_id": "RFP-20260803-AB12CD",
  "currency": "EUR",
  "generated_at": "2026-11-15T12:05:00+00:00",
  "client": {"name": "ModaViva, S.L.", "country": "Spain", "currency": "EUR"},
  "client_country": "Spain",
  "services_requested": ["warehousing", "reverse_logistics"],
  "sections": [
    {
      "department_id": "warehouse",
      "department_label": "Warehouse Operations",
      "responsible": "Ana Whitfield",
      "draft_content": "…",
      "draft_payload": {"…": "…"},
      "evaluation_results": {"…": "…"},
      "approval_status": "approved",
      "approver": "Ana Whitfield",
      "approved_at": "2026-11-15T12:00:00+00:00",
      "approval_comment": "Capacidad validada.",
      "provisional": false
    }
  ],
  "approved_by": [
    {
      "department_id": "warehouse",
      "department_label": "Warehouse Operations",
      "responsible": "Ana Whitfield",
      "approver": "Ana Whitfield",
      "approved_at": "2026-11-15T12:00:00+00:00",
      "comment": "Capacidad validada.",
      "provisional": false
    }
  ],
  "markdown": "# Propuesta comercial — ModaViva, S.L.\n…"
}
```

## Reglas de generación

1. Se genera **solo** si todas las secciones activas están `approved`.
2. El `final_gate` revalida el briefing §5 antes de escribir:
   - moneda del país (US→USD, Spain→EUR),
   - SLA 90% mensual,
   - devoluciones ≥ 48 h,
   - tabla de descuentos por volumen,
   - sin tarifas negociadas de transportistas.
3. Una sección `provisional` puede entrar si el humano la aprobó con
   `acknowledge_provisional=true`; la tabla de aprobaciones lo refleja.
4. Si el gate falla, no se escribe documento; el ticket pasa a
   `needs_human_review` y la traza registra las violaciones.
5. El Markdown incluye cabecera, tabla de aprobaciones, secciones consolidadas,
   condiciones comunes, descuentos y preguntas abiertas.

## Compatibilidad

- La Parte 2 sigue emitiendo `rfp-proposal-v1` sin cambios.
- La Parte 3 acepta tickets que llegan desde `esperando_aprobación` o
  `needs_human_review` (secciones provisionales).
- Un ticket `terminado` es terminal: no admite regeneración ni nuevas
  aprobaciones; para reabrir hay que iniciar un run nuevo desde la Parte 2.
- Regenerar la propuesta (Parte 2) invalida las aprobaciones anteriores: se
  limpian `approval_status`, `approval_interrupt_id` y `approval_packet`, y la
  Parte 3 arranca un `run-{n+1}` nuevo. Los checkpoints del run anterior quedan
  aislados por su `thread_id`.
