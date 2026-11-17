# Evidencias — ciclo NIST AI Security

Cada archivo se genera con un comando reproducible desde la raíz del
monorepo. Las salidas son de la rama `feature/nist-security-practices`
(2026-11-18).

| Archivo | Comando | Qué demuestra |
|---|---|---|
| `secret-scan.txt` | `bash scripts/security/check-secret-permissions.sh` + `git ls-files` | No hay `.env` trackeados, permisos `600`, sin claves en código |
| `harness-demo.txt` | `services/api/venv/bin/python scripts/demo_agent_harness.py` | Corpus de inyección, alcance, autorización y output guard |
| `injection-demo.txt` | `services/api/venv/bin/python scripts/security/prompt_injection_demo.py` | Casos directos e indirectos bloqueados/neutralizados (exit 0) |
| `agent-trace.json` + `agent-trace.txt` | `services/api/venv/bin/python scripts/security/agent_trace_demo.py --out ...` | Traza con ruta, nodos, fuentes, guardrails y tiempos |
| `rate-limit.txt` | `pytest -v` de los tests de rate limit | 429 + `Retry-After` en agente, knowledge, RFP y WebSocket |
| `human-approval.txt` | `pytest -v` de aprobación RFP + `scripts/rfp_e2e.py` | `interrupt()` humano, aprobador nombrado y `final_gate` |
| `test-results.txt` | Suites de API y pipelines | Estado de la suite completa tras los cambios |

> Los tests que requieren un LLM vivo no forman parte de esta evidencia: todo
> lo anterior se ejecuta sin red, con dobles deterministas.
