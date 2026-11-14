# Evidencia — ciclos completos de memoria

Dos ciclos completos (aprobado y rechazado) y un tercer ciclo de bloqueo por
contenido prohibido. La evidencia se genera con el endpoint real
`POST /agent/chat`, el store real (SQLite temporal) y los mismos servicios que
usa la API. El LLM se sustituye por dobles deterministas para que la prueba sea
reproducible sin red, Qdrant, MCP ni credenciales.

```bash
services/api/venv/bin/python scripts/demo_agent_memory.py
```

Salida completa (JSON) en la ejecución del script. A continuación se copian los
fragmentos relevantes; los identificadores y timestamps varían en cada corrida.

---

## Ciclo 1 — Aprobado: SEUR deja de cubrir la zona rural

### Turno 1 — propuesta en la misma respuesta

Petición:

```json
{"message": "En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que usar el carrier local desde el mes pasado.", "session_id": "demo-approved"}
```

Respuesta `200`:

```json
{
  "session_id": "demo-approved",
  "run_id": "run-propose_carrier",
  "answer": "Entendido: SEUR ya no cubre esa zona rural de Zaragoza.\n\n¿Quieres que lo recuerde para futuras conversaciones? Responde «sí» para guardarlo o «no» para descartarlo.",
  "memory": {
    "pending_proposal": {
      "id": "263b8b0a-...",
      "memory_type": "carrier_rule",
      "scope": {
        "kind": "carrier",
        "carrier": "SEUR",
        "country": "ES",
        "zone": "rural",
        "key": "carrier:SEUR:ES:rural",
        "label": "SEUR · ES · zona rural"
      },
      "fact": "SEUR ya no cubre la zona rural de Zaragoza; usar el carrier local desde el mes pasado.",
      "reason": "Corrección aportada por el usuario",
      "question": "¿Quieres que lo recuerde para futuras conversaciones? Responde «sí» para guardarlo o «no» para descartarlo."
    },
    "resolution": null,
    "blocked": null
  }
}
```

Estado: `agent_memory_proposals.status = pending`, sin entrada en
`agent_memory_entries`. Auditoría: `proposed`.

### Turno 2 — confirmación explícita

Petición: `{"message": "sí, guárdalo", "session_id": "demo-approved"}`

Respuesta `200`:

```json
{
  "answer": "Hecho. Lo recordaré en futuras conversaciones.",
  "memory": {
    "pending_proposal": null,
    "resolution": {
      "proposal_id": "263b8b0a-...",
      "decision": "approve",
      "status": "approved",
      "entry_id": "c4119e71-...",
      "message": "Hecho. Lo recordaré en futuras conversaciones."
    },
    "blocked": null
  }
}
```

Estado: propuesta `approved`; nueva entrada `active`, `version: 1`,
`scope_key: carrier:SEUR:ES:rural`, `review_at: +90 días`. Auditoría:
`approved` con `entry_id` y `scope_key`.

### Turno 3 — la memoria se usa en una interacción futura

Petición: `{"message": "¿Qué carrier usamos para la zona rural de Zaragoza?", "session_id": "demo-approved"}`

Respuesta `200`:

```json
{
  "answer": "Según la memoria aprobada: SEUR ya no cubre la zona rural de Zaragoza; usar el carrier local desde el mes pasado.",
  "memory": null
}
```

El `run_agent` de la demo recibió
`memory_context = [{scope_key: "carrier:SEUR:ES:rural", fact: "...", ...}]` y la
respuesta la cita. En el grafo real, `read_memory()` inyecta ese bloque en el
prompt y la traza lo refleja con `sources_used: ["rag", "memory"]` cuando el
modelo lo usa (evals
`test_no_context_answers_from_approved_memory_without_llm` y
`test_rag_generates_answer_and_proposal_in_a_single_call`).

---

## Ciclo 2 — Rechazado: preferencia de cliente de cosméticos

### Turno 1 — propuesta

Petición:

```json
{"message": "El cliente de cosméticos siempre quiere su reporte mensual con el desglose de devoluciones primero, antes que el volumen de envíos.", "session_id": "demo-rejected"}
```

Respuesta `200`:

```json
{
  "answer": "Anotado: el cliente de cosméticos prefiere devoluciones primero.\n\n¿Quieres que lo recuerde...?",
  "memory": {
    "pending_proposal": {
      "id": "d0015523-...",
      "memory_type": "client_preference",
      "scope": {"kind": "client", "client": "cosmeticos", "key": "client:cosmeticos"},
      "fact": "El cliente de cosméticos quiere el desglose de devoluciones primero en su reporte mensual."
    },
    "resolution": null,
    "blocked": null
  }
}
```

Estado: propuesta `pending`; sin entrada. Auditoría: `proposed`.

### Turno 2 — rechazo explícito

Petición: `{"message": "no, eso era solo para esta campaña", "session_id": "demo-rejected"}`

Respuesta `200`:

```json
{
  "answer": "Entendido. No guardaré esa información.",
  "memory": {
    "pending_proposal": null,
    "resolution": {
      "proposal_id": "d0015523-...",
      "decision": "reject",
      "status": "rejected",
      "entry_id": null,
      "message": "Entendido. No guardaré esa información."
    },
    "blocked": null
  }
}
```

Estado: propuesta `rejected`; `agent_memory_entries` sigue **sin** ninguna
entrada de cliente. Auditoría: `rejected` con `default_reject: false`.

### Turno 3 — la memoria no cambia

Petición: `{"message": "¿Cómo quiere el reporte el cliente de cosméticos?", "session_id": "demo-rejected"}`

Respuesta `200`:

```json
{
  "answer": "Respuesta a: ¿Cómo quiere el reporte el cliente de cosméticos? (sin memoria relevante)",
  "memory": null
}
```

El `run_agent` recibió `memory_context = []`. La preferencia no se recordó.

---

## Ciclo 3 — Bloqueado: dirección exacta de entrega (B2C/B2B)

Petición:

```json
{"message": "La entrega de SEUR en la zona rural de Zaragoza se hace en Calle Mayor 12, piso 3.", "session_id": "demo-blocked"}
```

El generador propone un hecho con la dirección, pero la validación determinista
lo bloquea antes de crear la propuesta:

```json
{
  "answer": "Entendido.",
  "memory": {
    "pending_proposal": null,
    "resolution": null,
    "blocked": "exact_address"
  }
}
```

Estado: no se crea propuesta ni entrada. Auditoría: `blocked` con
`validation_code: exact_address`. El mensaje origen se guarda **redactado**:

```text
La entrega de SEUR en la zona rural de Zaragoza se hace en [REDACTED_ADDRESS].
```

No se persiste la dirección completa en claro.

---

## Snapshot final del store

```json
{
  "entries": [
    {
      "memory_type": "carrier_rule",
      "scope_key": "carrier:SEUR:ES:rural",
      "fact": "SEUR ya no cubre la zona rural de Zaragoza; usar el carrier local desde el mes pasado.",
      "status": "active",
      "version": 1
    }
  ],
  "proposals": [
    {"memory_type": "carrier_rule", "status": "approved", "decision_label": "approve", "decision_message": "sí, guárdalo"},
    {"memory_type": "client_preference", "status": "rejected", "decision_label": "reject", "decision_message": "no, eso era solo para esta campaña"}
  ],
  "audit": [
    {"action": "proposed"},
    {"action": "approved"},
    {"action": "proposed"},
    {"action": "rejected"},
    {"action": "blocked"}
  ]
}
```

Se cumple:

- Propuesta visible en la misma conversación, no en un canal aparte.
- Ninguna escritura sin decisión explícita: el primer ciclo escribe solo en el
  turno 2; el segundo no escribe nunca.
- Una sola propuesta pendiente por usuario (índice único
  `ux_agent_memory_pending_user`).
- Silencio/ambigüedad → rechazo por defecto (test
  `test_unrelated_message_rejects_pending_by_default`).
- Auditoría completa de propuesta, resultado, mensaje y timestamp, aprobada o
  rechazada.
- El ciclo bloqueado demuestra que la dirección B2C/B2B nunca entra.

---

## Evals y tests que respaldan la evidencia

```text
services/api/tests/test_agent_memory.py        57 passed
services/api/tests/test_agent_chat.py          13 passed
tests/pipelines/test_agent_memory_evals.py     14 passed
tests/pipelines/test_agent_evals.py            23 passed (regresión)
services/api (suite completa)                 329 passed
```

Comandos:

```bash
cd services/api && source venv/bin/activate
python -m pytest tests/test_agent_memory.py tests/test_agent_chat.py -q
python -m pytest -q

cd ../..
uv run pytest tests/pipelines/test_agent_evals.py \
  tests/pipelines/test_agent_memory_evals.py -q

services/api/venv/bin/python scripts/demo_agent_memory.py
```

## Nota sobre la ejecución real

La demo usa dobles del LLM para que la evidencia sea determinista. El flujo de
producción es el mismo: `POST /agent/chat` → `run_agent` con el generador real
(`generate_with_memory`, una sola llamada para respuesta + propuesta) →
validación → store. Para probarlo con el LLM real y Qdrant/MCP levantados basta
con autenticarse contra la API y repetir las mismas peticiones; no hay ninguna
diferencia de contrato.
