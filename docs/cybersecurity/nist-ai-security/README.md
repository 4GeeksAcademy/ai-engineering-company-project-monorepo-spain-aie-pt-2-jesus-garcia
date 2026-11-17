# Seguridad de IA en TrackFlow — Informe NIST AI RMF

**Empresa:** TrackFlow (Los Ángeles, EE. UU. · Zaragoza, España)  
**Unidad:** TrackFlow Tech  
**Fecha:** 2026-11-17  
**Rama:** `feature/nist-security-practices`  
**Briefing aplicable:** [`docs/cybersecurity/nist-security-practices.md`](../nist-security-practices.md)

Este directorio es la **carpeta de entrega** del ciclo de seguridad de IA. Contiene
el informe NIST, el inventario de sistemas, la documentación del caso de prompt
injection y las evidencias reproducibles.

| Documento | Para qué sirve |
|---|---|
| [`ai-system-inventory.md`](./ai-system-inventory.md) | Inventario completo (implementado y planificado), responsable por componente y control cuando el modelo o la tool es de un tercero |
| [`nist-ai-rmf-report.md`](./nist-ai-rmf-report.md) | Informe con las seis funciones NIST, acciones priorizadas, marco regulatorio (RGPD/AEPD y CCPA/CPRA) y registro de brechas |
| [`prompt-injection-tests.md`](./prompt-injection-tests.md) | Caso de prueba reproducible: inyección directa e indirecta bloqueada o neutralizada |
| [`evidence/`](./evidence/README.md) | Salidas reales de los comandos que sostienen cada afirmación |

---

## 1. Mapa de entradas externas al modelo

Antes de tocar código se identificó **todo punto donde un modelo de lenguaje
recibe contenido que no ha escrito el sistema**. La columna *confianza* usa
estas etiquetas:

| Etiqueta | Origen | ¿Puede contener instrucciones? |
|---|---|---|
| **A** | Usuario autenticado (B2B/B2C/manager) | Sí, es input hostil por diseño |
| **B** | Documento externo (PDF RFP, base de conocimiento semántica) | Sí, inyección indirecta |
| **C** | Resultado de una tool/MCP | Sí, si el sistema de origen está comprometido |
| **D** | Memoria aprobada por un humano | Sí, indirecta y persistente |
| **E** | Salida de otro LLM (handoff, feedback de evaluador) | Sí, propagación entre agentes |
| **F** | Documento interno autorado por TrackFlow (KB) | Bajo, pero se trata igual que B en el agente |

### 1.1 Diagrama de flujo

```
                         ┌──────────────────────────────────────────────┐
 [B2C/B2B] pregunta ────►│ POST /agent/query                            │
 [B2C/B2B] mensaje  ────►│ POST /agent/chat                             │
 [B2C/B2B] WS frame ────►│ WS   /chat/ws  (user_message, interrupt)     │
 [manager] pregunta ────►│ POST /knowledge/query                        │
                         └───────────────┬──────────────────────────────┘
                                         │  (A)
                       ┌─────────────────▼──────────────────┐
                       │ screen_input  (harness)            │
                       │  · estructural · inyección         │
                       │  · autorización de pedidos         │
                       │  · alcance / uso personal          │
                       └─────────────────┬──────────────────┘
                                         │ allow
                    ┌────────────────────▼─────────────────────┐
                    │ LangGraph: router → retrieve → generate  │
                    │        │            │           │        │
                    │        │            │           │        │
                    │        │   ┌────────▼───────┐   │        │
                    │        │   │ Qdrant chunks  │   │        │
                    │        │   │   (B/F)        │   │        │
                    │        │   └────────────────┘   │        │
                    │        │   ┌────────────────────┐        │
                    │        └──►│ MCP tools          │        │
                    │            │ incidents/inventory│        │
                    │            │   (C)              │        │
                    │            └────────┬───────────┘        │
                    │   ┌─────────────────▼──────────────┐    │
                    │   │ memoria aprobada (D)           │    │
                    │   └─────────────────┬──────────────┘    │
                    │                     ▼                   │
                    │            generate_answer ──► LLM      │
                    └────────────────────┬────────────────────┘
                                         │
                       ┌─────────────────▼──────────────────┐
                       │ validate_output (harness)          │
                       │  · fuga de prompt · PII · tarifas  │
                       │  · pedido ajeno · política país    │
                       └────────────────────────────────────┘

 [manager] PDF RFP ──► markitdown ─► classifier ─► metadata ─► orchestrator
                                         │            │            │
                                         ▼            ▼            ▼
                                      workers (excerpts B) ─► synthesizer ─► handoff (E)
                                                                              │
 [humano] comentario de aprobación (A) ◄──────────────────────────────────────┤
                    │                                                         ▼
                    └──────────────────────────► generadores/evaluadores (E)
```

### 1.2 Inventario de puntos de entrada

| # | Punto de entrada | Archivo | Modelo | Confianza | Desde | Control actual |
|---|---|---|---|---|---|---|
| 1 | `POST /agent/query` | `services/api/app/routes/agent.py` | generación + embeddings | A | usuario autenticado | `screen_input` → grafo → `validate_output`; rate limit 60/min |
| 2 | `POST /agent/chat` | `services/api/app/routes/agent_memory.py` | generación + embeddings + memoria | A + D | usuario autenticado | igual que (1) + gate de memoria y confirmación humana |
| 3 | WebSocket `user_message` | `services/api/app/routes/chat.py` | generación + embeddings | A | usuario autenticado | mismo borde del agente + rate limit por usuario/sesión |
| 4 | WebSocket `interrupt_requested.new_input` | `services/api/app/routes/chat.py` | generación | A | usuario autenticado | se reinyecta como nuevo turno (pasa por `screen_input`) |
| 5 | `POST /knowledge/query` | `services/api/app/routes/knowledge.py` | generación + embeddings | A + B/F | manager/admin | screening de inyección + aislamiento de contexto + rate limit |
| 6 | Chunks recuperados de Qdrant | `data/pipelines/rag.py` | generación | B/F | base de conocimiento | `isolate_context`: neutraliza líneas de instrucción y delimita `<untrusted_content>` |
| 7 | Resultado de tools MCP | `services/api/app/agent/tools/` | generación | C | MCP server / API | `sanitize_external_text` + scope `mcp:read` + timeout/fallback |
| 8 | Memoria aprobada | `services/api/app/agent/memory/` | generación | D | propuesta validada y aprobada por manager | se filtra por rol, se redacta PII y se trunca |
| 9 | Historial de conversación | `services/api/app/agent/memory/prompts.py` | generación | A | turnos previos de la sesión | acotado y redactado; los turnos bloqueados no entran |
| 10 | PDF RFP → markdown | `data/pipelines/rfp_intake/` | clasificador, metadatos, orquestador, workers, synthesizer | B | documento externo subido | neutralización de instrucciones + regla "documento = datos" |
| 11 | Handoff RFP | `data/pipelines/rfp_proposal/` | generadores y evaluadores | E | salida del pipeline de intake | contrato Pydantic + guardarraíl numérico + regla de datos |
| 12 | Comentario humano de aprobación | `data/pipelines/rfp_approval/approval_graph.py` | generador de sección | A | manager que revisa | validación de decisión + regeneración acotada a una sección |
| 13 | Clientes MCP externos | `mcps/trackflow-mcp/` | (el modelo vive en el cliente) | A/C | terceros con OAuth | OAuth 2.1 + scopes `mcp:read`/`mcp:write` + tools con guard |
| 14 | Indexación de la KB | `data/process/rag_index.py` | embeddings | F | documentos internos | solo lectura de `docs/company-knowledge-base/`; colección versionada |

> Los componentes que **no** llaman a un LLM (API de inventario, analizador de
> CSV de incidencias, modelo de forecast de ventas, telemetría y SSE) se listan
> igualmente en el inventario para dejar claro su alcance.

### 1.3 Cómo se trata cada etiqueta

- **A (usuario):** se normaliza Unicode, se eliminan caracteres de control y se
  aplican patrones de inyección; el contenido nunca se concatena con el system
  prompt.
- **B (documentos):** se eliminan caracteres de control, se acota la longitud,
  se neutralizan líneas que parecen instrucciones y se encierran en
  `<untrusted_content>`. El system prompt declara que ese bloque es dato.
- **C (tools):** misma sanitización que B; el agente solo tiene `mcp:read`.
- **D (memoria):** propuesta → validación → aprobación humana → inyección
  acotada y filtrada por rol.
- **E (otro LLM):** contratos Pydantic, guardarraíl numérico y revisión humana
  antes de publicar.

---

## 2. Gestión actual de credenciales y API keys

Revisión de `.env.example` (raíz, `services/api` y `mcps/trackflow-mcp`):

| Secreto | Dónde se define | Quién lo consume | Estado |
|---|---|---|---|
| `SECRET_KEY` (JWT) | `.env` raíz / `services/api/.env` | `app/core/security.py` | Obligatoria en producción (≥ 32 caracteres, sin placeholders) |
| `RESEND_API_KEY` | `.env` | `app/email_service.py` | Vacía → stub por consola; nunca en código |
| `LLM_API_KEY` | `services/api/.env` | RAG, agente, RFP, memoria | Solo entorno; el código falla de forma explícita si falta |
| `QDRANT_API_KEY` | `services/api/.env` | Cliente Qdrant | Opcional en local, obligatoria si Qdrant se expone |
| `DATABASE_URL` | `.env` | SQLModel/Postgres | Incluye la contraseña de Supabase; nunca en logs |
| `MCP_OAUTH_CLIENT_SECRET` | `.env` | `app/agent/tools/mcp_auth.py` | Token M2M; el agente no comparte el JWT local |
| `TRACKFLOW_API_PASSWORD` | `.env` | MCP server | Cuenta de servicio dedicada; producción rechaza `admin123` y < 12 caracteres |
| `AUTH0_M2M_CLIENT_*` | `.env` | Scripts de validación | No los usa el servidor |

Controles verificados:

1. **Ningún secreto real está en el repositorio.** `git ls-files` no incluye
   ningún `.env` (solo `.env.example`).
2. **`.env` con permisos `600`** en raíz, `services/api` y `mcps/trackflow-mcp`
   (verificado con `stat`).
3. **Validación fail-fast en producción** (`app/core/config.py`): `SECRET_KEY`
   débil, `ALLOWED_ORIGINS` vacía o con `*`, y `TRACKFLOW_API_PASSWORD` débil
   abortan el arranque.
4. **Rotación operativa pendiente:** las claves reales deben rotarse en el vault
   del despliegue; el repositorio solo garantiza que no se filtran.
5. **Credenciales de desarrollo:** los seeders y scripts de smoke ya no
   contienen contraseñas literales; se leen de `SEED_*` o se generan y se
   imprimen una sola vez (ver `evidence/secret-scan.txt`).

> **Limitación:** no hay vault externo (Vault/SSM/Doppler) en este fork; el
> "vault" es el `.env` del host con permisos restringidos y variables inyectadas
> por el orquestador. Se documenta como brecha en el informe NIST.

---

## 3. Cómo reproducir las evidencias

```bash
# 1. Escaneo de secretos y permisos
bash scripts/security/check-secret-permissions.sh
git ls-files | grep -E '(^|/)\.env$' || echo "OK: ningún .env trackeado"

# 2. Demo determinista del harness (sin red ni LLM)
services/api/venv/bin/python scripts/demo_agent_harness.py

# 3. Demo de prompt injection (directa e indirecta)
services/api/venv/bin/python scripts/security/prompt_injection_demo.py

# 4. Tests de inyección, harness, knowledge y rate limiting
cd services/api && ./venv/bin/python -m pytest \
  tests/test_agent_harness_*.py tests/test_knowledge.py \
  tests/test_security_hardening.py tests/test_rfp_api.py -q

# 5. Tests del pipeline RFP (saneado de documentos)
uv run pytest tests/pipelines/test_rfp_injection.py -q

# 6. Flujo de aprobación humana RFP (sin red)
services/api/venv/bin/python scripts/rfp_e2e.py
```

Cada salida se archiva en [`evidence/`](./evidence/README.md).
