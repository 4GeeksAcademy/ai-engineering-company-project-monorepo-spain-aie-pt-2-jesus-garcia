# Contrato de handoff — RFP Intake → Parte 2

La Parte 2 **no reparsea el PDF**. Arranca con `ticket_id` + el payload del
synthesizer persistido en PostgreSQL.

## Dónde vive

- `rfp_ticket.handoff_status = 'ready'`
- `rfp_ticket.handoff_payload` (JSONB)
- `rfp_ticket.handoff_at`
- Endpoint de lectura: `GET /rfp/handoff/{ticket_id}` (admin/manager)

La Parte 2 puede consultar tickets listos con:

```
GET /rfp/tickets?status=analisis_completo
```

o leer directamente `rfp_ticket` donde `handoff_status = 'ready'`.

## Forma del payload

```json
{
  "contract_version": "rfp-intake-v1",
  "ticket_id": "4f4d...",
  "rfp_id": "RFP-20260803-AB12CD",
  "status": "analisis_completo",
  "generated_at": "2026-11-15T10:00:00+00:00",
  "client": {
    "name": "ModaViva, S.L.",
    "country": "Spain",
    "currency": "EUR",
    "contact": {"name": "Elena Bosch", "role": "Directora de Operaciones"}
  },
  "currency": "EUR",
  "services_requested": ["warehousing", "reverse_logistics"],
  "unknown_services": [],
  "rfp_facts": {
    "monthly_volume": null,
    "sku_count": 15000,
    "return_volume": null,
    "return_rate": null,
    "deadline": "2026-08-28",
    "budget_range": null
  },
  "departments": [
    {
      "department_id": "warehouse",
      "department_label": "Warehouse Operations",
      "responsible": "Ana Whitfield",
      "focus": "Capacidad para 15.000 SKUs",
      "key_aspects": [
        {
          "aspect": "Volumen de SKUs",
          "detail": "La RFP declara 15.000 SKUs en un centro cercano a Zaragoza.",
          "evidence": "Almacenamiento de aproximadamente 15.000 SKUs",
          "confidence": "high"
        }
      ],
      "open_questions": [
        "Falta el volumen mensual de pedidos: confirmarlo con el cliente..."
      ]
    }
  ],
  "questions_to_ask": [
    {
      "department_id": "warehouse",
      "responsible": "Ana Whitfield",
      "question": "Falta el volumen mensual de pedidos..."
    }
  ],
  "conflicts": [],
  "sales_summary": "- ModaViva (España, EUR) pide almacenamiento y devoluciones...",
  "next_steps": [
    {
      "department_id": "warehouse",
      "responsible": "Ana Whitfield",
      "action": "Pedir capacidad, coste por pallet/SKU, onboarding..."
    }
  ],
  "source": {
    "pdf_path": "/app/data/raw/rfp/<ticket_id>/trackflow-request-1.pdf",
    "markdown_path": "/app/data/raw/rfp/<ticket_id>/rfp.md",
    "document_metadata": {"page_count": 2, "converter": "markitdown"},
    "readability_metrics": {"word_count": 206, "estimated_llm_tokens": 351},
    "classification": {"document_type": "formal_rfp", "confidence": 0.96}
  }
}
```

## Reglas para la Parte 2

1. Usar `departments[].department_id` como lista cerrada de secciones activas.
2. No añadir departamentos ni cambiar `currency`; ambos son canónicos.
3. Tratar `key_aspects` como material de partida, no como texto final.
4. Respetar `open_questions`: si faltan datos, la propuesta debe pedirlos, no
   inventarlos.
5. `source.pdf_path` / `source.markdown_path` existen solo para trazabilidad;
   la Parte 2 no necesita reconvertir el PDF.
6. `rfp_facts` es el bloque canónico de datos de la RFP que la Parte 2 usa para
   cotizar sin reparsear. Campo aditivo del contrato `rfp-intake-v1`: si un
   payload antiguo no lo trae, la Parte 2 lee los mismos datos de
   `rfp_metadata`.
7. Los campos `draft_content`, `evaluation_results`, `approval_status`,
   `approver` y `approved_at` de `rfp_department_section` quedan preparados para
   escribir el resultado de la Parte 2/3 sin migrar el esquema.
