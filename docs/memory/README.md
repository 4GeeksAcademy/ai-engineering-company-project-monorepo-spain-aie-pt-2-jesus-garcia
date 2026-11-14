# Memoria y harness del agente de TrackFlow

- [`agent-harnessing.md`](agent-harnessing.md) — enunciado del aseguramiento
  (system prompt, guardrails, anti-inyección y observabilidad).
- [`agent-harnessing-design.md`](agent-harnessing-design.md) — arquitectura del
  harness, capas, taxonomía de fallos y decisiones.
- [`agent-harnessing-evidence.md`](agent-harnessing-evidence.md) — jailbreaks,
  pedido ajeno, mezcla de políticas, inyección RAG/tool, salida filtrada,
  resumen de guardrails y sección lista para el PR.
- [`agent-memory-1.md`](agent-memory-1.md) — enunciado de la tarea y
  restricciones de la empresa.
- [`agent-memory-design.md`](agent-memory-design.md) — arquitectura, tipos de
  memoria, qué nunca se guarda, auto-evaluación, confirmación, auditoría,
  consolidación, anti-envenenamiento y justificación de no multi-agente.
- [`agent-memory-evidence.md`](agent-memory-evidence.md) — ciclos completos:
  aprobado, rechazado y bloqueado por dirección exacta.

Implementación de memoria:

- `services/api/app/agent/memory/` — store, modelos, validación, gate, prompts,
  generación con memoria, evaluación, intención, consolidación y servicio.
- `services/api/app/routes/agent_memory.py` — `/agent/chat` y administración.
- `services/api/migrations/0004_agent_memory.sql` — tablas PostgreSQL/Supabase.
- `scripts/demo_agent_memory.py` — evidencia reproducible sin red.

Implementación del harness:

- `services/api/app/agent/harness/` — prompt de CX, alcance, inyección,
  autorización de pedidos, aislamiento externo, salida y observabilidad.
- `services/api/app/routes/agent_harness.py` — `GET /agent/harness/stats`.
- `services/api/migrations/0005_customer_orders.sql` +
  `services/api/seed_customer_orders.py` — propiedad de pedidos de demo.
- `services/api/tests/test_agent_harness_*.py` +
  `services/api/tests/fixtures/harness_corpus.json` — tests deterministas.
- `scripts/demo_agent_harness.py` — demo reproducible sin red.

Verificación rápida:

```bash
cd services/api && source venv/bin/activate
python -m pytest tests/test_agent_memory.py tests/test_agent_chat.py -q
python -m pytest tests/test_agent_harness_*.py -q
cd ../.. && uv run pytest tests/pipelines/test_agent_evals.py \
  tests/pipelines/test_agent_memory_evals.py -q
services/api/venv/bin/python scripts/demo_agent_memory.py
services/api/venv/bin/python scripts/demo_agent_harness.py
```
