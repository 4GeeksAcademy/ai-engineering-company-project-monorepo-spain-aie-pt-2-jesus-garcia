# Memoria del agente de TrackFlow

- [`agent-memory-1.md`](agent-memory-1.md) — enunciado de la tarea y
  restricciones de la empresa.
- [`agent-memory-design.md`](agent-memory-design.md) — arquitectura, tipos de
  memoria, qué nunca se guarda, auto-evaluación, confirmación, auditoría,
  consolidación, anti-envenenamiento y justificación de no multi-agente.
- [`agent-memory-evidence.md`](agent-memory-evidence.md) — ciclos completos:
  aprobado, rechazado y bloqueado por dirección exacta.

Implementación:

- `services/api/app/agent/memory/` — store, modelos, validación, gate, prompts,
  generación con memoria, evaluación, intención, consolidación y servicio.
- `services/api/app/routes/agent_memory.py` — `/agent/chat` y administración.
- `services/api/migrations/0004_agent_memory.sql` — tablas PostgreSQL/Supabase.
- `scripts/demo_agent_memory.py` — evidencia reproducible sin red.

Verificación rápida:

```bash
cd services/api && source venv/bin/activate
python -m pytest tests/test_agent_memory.py tests/test_agent_chat.py -q
cd ../.. && uv run pytest tests/pipelines/test_agent_evals.py \
  tests/pipelines/test_agent_memory_evals.py -q
services/api/venv/bin/python scripts/demo_agent_memory.py
```
