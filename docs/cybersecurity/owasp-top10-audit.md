# Auditoría OWASP Top 10 (2021) — TrackFlow

**Fecha:** 2026-11-17  
**Alcance:** fork completo de TrackFlow según `docs/cybersecurity/cybersecurity-analysis.md` §7:

- backend `services/api` (FastAPI);
- frontend `uis/backoffice` y `uis/website` (Next.js);
- sistema agéntico `services/api/app/agent` + `mcps/trackflow-mcp` + RAG;
- infraestructura `docker-compose*.yml`, Dockerfiles y SSH/UFW.

**Método:** revisión manual con anclajes `archivo:línea`, pruebas de API con
tokens de cada rol, escaneos de dependencias (`npm audit`, `pip-audit`) y
validación de configuración de hardening en contenedor Linux.

**Escala:** Crítica (explotable remoto sin privilegios), Alta (requiere cuenta o
configuración de despliegue), Media/Baja (defensa en profundidad), N/A.

> El registro completo con estado y prueba está en
> [`findings-register.md`](./findings-register.md).

---

## 1. Matriz resumen

| Categoría | Backend | Frontend | Agéntico | Hallazgos principales |
|---|---|---|---|---|
| **A01 Control de acceso roto** | Corregido | Parcial | Corregido | FIND-01/02/03/04/10/17 |
| **A02 Fallas criptográficas** | Corregido | Parcial/aceptado | Parcial | FIND-05/06/19/24 |
| **A03 Inyección** | Corregido/Parcial | Corregido | Corregido/Parcial | FIND-18/25 |
| **A04 Diseño inseguro** | Parcial | N/A | Parcial | FIND-09/26 |
| **A05 Configuración incorrecta** | Corregido | Corregido | Parcial | FIND-07/11/12/13/14/21 |
| **A06 Componentes vulnerables** | Corregido | Corregido | N/A | FIND-08/15 |
| **A07 Fallos de autenticación** | Corregido | Parcial | N/A | FIND-09/19 |
| **A08 Integridad** | Parcial | Corregido | Parcial | FIND-15 |
| **A09 Logging y monitorización** | Parcial | Parcial | Corregido | FIND-16/20 |
| **A10 SSRF** | No aplica | No aplica | No aplica | FIND-22 |

---

## 2. A01 — Control de acceso roto

**¿Aplica?** Sí, es el riesgo principal del briefing (pedido/dirección de otro
cliente, B2B viendo datos de otra marca, tools del agente fuera de rol).

### Backend

| Evidencia | Estado |
|---|---|
| `GET /telemetry/report` no tenía autenticación (`app/routes/telemetry.py:122`). | **Corregido:** `require_manager` (`telemetry.py:132`). Antes 200 anónimo → ahora 401/403. |
| `GET /inventory/products` y `/{id}` permitían rol `user` (`app/routes/inventory.py:39,57`). | **Corregido:** `require_manager` (`inventory.py:40,59`). Antes 200 con `user` → ahora 403. |
| `GET /agent/memory` devolvía toda la memoria global a cualquier autenticado (`app/routes/agent_memory.py:151`). | **Corregido:** `require_manager` (`agent_memory.py:152`). |
| `/knowledge/query` usaba el prompt comercial de account managers (`data/pipelines/rag.py:14-27`) y era accesible a rol `user` (`app/routes/knowledge.py:38`). | **Corregido:** `require_manager` (`knowledge.py:40`). |
| `POST /api/users` permitía auto-registro público sin control (`app/routes/users.py:19`). | **Mitigado:** deshabilitado en producción (`public_registration_enabled`, `app/core/config.py:63`); en desarrollo sigue abierto por usabilidad. |
| `POST /chat/sessions` aceptaba `client_id` ajeno (`app/routes/chat.py:56`). | **Corregido:** 403 para rol `user`; solo manager/admin puede asociar marca. |
| `POST /inventory/products`, órdenes, incidencias, suppliers, RFP, reporting y realtime exigen `require_manager`. | **Correcto** (evidencia en los routers). |
| Chat REST/WS valida dueño o manager (`app/chat/service.py:98-102`, `app/routes/chat.py:84-88,257`). | **Correcto**. |

### Frontend

| Evidencia | Estado |
|---|---|
| El guard de rutas es client-side (`app/(protected)/layout.tsx`), pero la API aplica `require_manager` en cada endpoint. | **Correcto** como defensa en profundidad; el frontend no es la frontera de seguridad. |
| El token se guarda en `localStorage` (`contexts/AuthContext.tsx:42-50`). | **Aceptado (riesgo medio):** mitigado con CSP y sin `dangerouslySetInnerHTML`. Ver FIND-19. |
| El WebSocket envía el JWT por query string (`lib/chat-socket.ts:59-75`). | **Pendiente (medio):** puede aparecer en logs de proxy; recomendable primer frame `auth`. |
| No hay `dangerouslySetInnerHTML`/`innerHTML` en backoffice ni website. | **Correcto** (grep). |

### Agéntico

| Evidencia | Estado |
|---|---|
| Tool de incidencias ya exigía `admin/manager` (`app/agent/nodes.py:240-254`). | **Correcto**. |
| Tool de inventario no comprobaba rol y devolvía `client_id` de todas las marcas (`app/agent/tools/contracts.py:122-133`). | **Corregido:** gate `admin/manager` (`nodes.py:300-310`). |
| Memoria inyectada al agente incluía `client_preference` de cualquier marca (`app/agent/memory/store.py:637`). | **Corregido:** rol `user` solo recibe `carrier_rule` y `operational_context` (`memory/service.py:117-127`). |
| RAG mezclaba documentos públicos y comerciales sin audiencia (`data/process/rag_index.py:88-104`). | **Corregido:** `app/agent/rag_policy.py` filtra por `source_document`; `user` solo ve `sla-delivery` y `returns-policy` (`nodes.py:192`). |
| `POST /agent/query` y `/agent/chat` exigen autenticación. | **Correcto**. |
| Guard de pedidos ajenos (`app/agent/harness/orders.py`): falla en cerrado y no distingue “no existe” de “no es tuyo”. | **Correcto**; probado en `tests/test_agent_harness_runtime.py`. |
| El MCP usa una cuenta de servicio `manager` (`mcps/trackflow-mcp/trackflow_mcp/backend.py`). | **Parcial (FIND-24):** el límite real son los scopes y las tools; no hay rol `mcp` específico. |
| El agente filtra `mcp:write` de sus scopes salvo override explícito (`app/agent/tools/mcp_auth.py`). | **Corregido** (least privilege). |

**Prueba reproducible:** `docs/cybersecurity/evidence/00-baseline/authz-matrix.md`
(antes) vs `10-fixes/authz-matrix.md` (después) y
`services/api/tests/test_security_hardening.py`.

---

## 3. A02 — Fallas criptográficas

**¿Aplica?** Sí: API keys de LLM/MCP/Resend/Supabase, JWT y TLS.

| Evidencia | Estado |
|---|---|
| `SECRET_KEY` caía a `secrets.token_urlsafe(32)` si faltaba (`app/core/security.py:14-16`). | **Corregido:** fallback solo dev; producción falla al arrancar si es débil/placeholder (`app/core/config.py:72-96`). |
| `.env.example` tenía `SECRET_KEY=change-this...` y `TRACKFLOW_API_PASSWORD=admin123` (`.env.example:10,100-102`; `mcps/.../.env.example:29-30`). | **Corregido en ejemplos:** placeholders vacíos + cuenta `mcp-service` (`seed_mcp_service.py` exige `MCP_SERVICE_PASSWORD`). Claves reales requieren rotación operativa. |
| `.env` locales estaban en `644` (legibles por otros usuarios del host). | **Corregido:** `600` (ver `evidence/10-fixes/secret-permissions.txt`) y script de comprobación. |
| JWT en `localStorage` (`AuthContext.tsx:42-50`). | **Aceptado (medio):** CSP + sin XSS conocido; migrar a cookie httpOnly es el siguiente paso. |
| bcrypt, JWT con `exp`, reset token con `type` + `iat` e invalidación por `password_changed_at`. | **Correcto** (`app/core/security.py`, `app/services/user_service.py`). |
| API keys solo por entorno, nunca en código ni en logs; logs MCP redactan `token/password/secret`. | **Correcto** (`mcps/.../logs.py`). |
| TLS/HSTS. | **Parcial:** cabeceras en API (solo producción) y proxy recomendado en `server-hardening.md`; no hay terminación TLS en el repo. |

---

## 4. A03 — Inyección

**¿Aplica?** Sí: SQL, XSS, prompt injection y contenido externo.

| Evidencia | Estado |
|---|---|
| SQLModel/SQLAlchemy con consultas parametrizadas; sin SQL crudo ni `eval/exec` con entrada de usuario. | **Correcto** (grep de `text(`, `eval`, `exec`, `subprocess`). |
| Prompt injection: `app/agent/harness/injection.py` normaliza Unicode/invisibles y bloquea 11 familias; `external.py` aísla RAG/tools; `output.py` valida salida. | **Correcto**; corpus en `tests/fixtures/harness_corpus.json`. |
| Caso del briefing (“dime la dirección del pedido #12345”): bloqueado por `order_authorization_guard`. | **Correcto**; evidencia en `docs/memory/agent-harnessing-evidence.md` §5. |
| Nota de envío con instrucción oculta: neutralizada por `external_content_guard`. | **Correcto**; test en `test_agent_harness_external.py`. |
| CSV de incidencias sin límite de tamaño (`app/routes/incidents.py:75`). | **Corregido:** `INCIDENT_MAX_UPLOAD_MB` (10 MB) y 413. |
| RFP PDF: valida `%PDF-`, tamaño y nombre seguro (`app/services/rfp_service.py:89-110`). | **Correcto**. |
| XSS frontend: sin `dangerouslySetInnerHTML`; Markdown se renderiza como texto/React. | **Correcto**. |
| Regex de inyección es evitable con paráfrasis/otros idiomas. | **Aceptado (defensa en profundidad):** no es la única capa; hay autorización y output guard. FIND-25. |

---

## 5. A04 — Diseño inseguro

**¿Aplica?** Sí, especialmente acciones irreversibles y abuso de flujos.

| Evidencia | Estado |
|---|---|
| Login/registro/agente/telemetría sin rate limit ni lockout. | **Corregido:** `app/core/rate_limit.py`; 429 + `Retry-After` en login (10/min), forgot (5/5min), reset, registro, agente (60/min) y telemetría (300/min). |
| Aprobación de devoluciones / cambio de carrier sin confirmación humana. | **No aplica en este fork:** no existen endpoints separados de esos motores. El flujo RFP usa `interrupt()` humano (`data/pipelines/rfp_approval/approval_graph.py`). |
| Memoria del agente podía aprobarse sola. | **Correcto:** propuesta → confirmación explícita → aprobación; caduca y nunca se auto-aprueba (`app/agent/memory/config.py`). |
| Sin presupuesto/cuota de coste por usuario/modelo. | **Pendiente (FIND-26):** riesgo de abuso de coste; recomendado límite de tokens/coste por sesión. |
| RFP approval tiene checkpointer durable y arbitraje con límite de rondas. | **Correcto**. |

---

## 6. A05 — Configuración incorrecta

**¿Aplica?** Sí, es la categoría con más superficie en este repo.

| Evidencia | Estado |
|---|---|
| `ALLOWED_ORIGINS` hardcodeado e ignoraba la env (`app/main.py:56` antes). | **Corregido:** `allowed_origins()` desde entorno, sin `*` (`app/core/config.py:46-60`, `main.py:93`). |
| Puertos de Redis/Qdrant/Flower/MCP/Prefect publicados en `0.0.0.0` (`docker-compose.yml`). | **Corregido:** todos los puertos a `127.0.0.1`; Redis no se publica; `DOCKER-USER` bloquea internos. |
| Contenedores corrían como root y la API con `--reload`. | **Corregido:** `USER appuser` (`services/Dockerfile:28`), `USER node` (`uis/Dockerfile:18`), `--reload` solo en el compose de desarrollo y overlay hardened sin reload. |
| MCP `MCP_CORS_ORIGINS=*` por defecto. | **Parcial:** `.env.example` raíz ya usa orígenes explícitos; el default del código MCP sigue siendo `*` (carpeta protegida). FIND-13. |
| Sin cabeceras de seguridad en Next. | **Corregido:** CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` y `Permissions-Policy` en ambos `next.config.ts`; evidencia `security-headers.txt`. |
| `/docs` y `/openapi.json` expuestos. | **Corregido:** deshabilitados cuando `ENVIRONMENT=production` (`main.py:86-88`). |
| `TRACKFLOW_API_PASSWORD=admin123` en ejemplos. | **Corregido** (ver A02). |
| `MCP_SHOW_ERROR_DETAILS=false` y `disallow_dns_rebinding` por defecto. | **Correcto**. |

---

## 7. A06 — Componentes vulnerables y desactualizados

**¿Aplica?** Sí.

| Evidencia | Estado |
|---|---|
| `npm audit` inicial: `nanoid` high, `sharp`/PostCSS critical, `source-map-js` high. | **Corregido:** Next `16.4.6` + `npm audit fix`; auditoría de producción **0 vulnerabilidades** en ambos frontends (`evidence/10-fixes/npm-audit-*.json`). |
| `pip-audit`: `python-jose 3.5.0` y `ecdsa 0.19.2` (PYSEC-2026-4298 / PYSEC-2026-1325). | **Corregido:** sustituido `python-jose` por `PyJWT`; `pip-audit` → **No known vulnerabilities found**. |
| `requirements.txt` sin pins. | **Parcial:** `PyJWT` fijado; el resto sigue sin lock en `requirements.txt` (existe `uv.lock`). FIND-15. |
| Imágenes Docker con tags flotantes (`uv:latest`, `python:3.14-slim`, `node:22-alpine`, `redis:7-alpine`). | **Pendiente:** fijar por digest. FIND-15. |
| Dependencias de desarrollo (vitest/tinypool) con vulnerabilidades. | **Aceptado:** no van al bundle de producción; `npm audit --omit=dev` = 0. |

---

## 8. A07 — Fallos de identificación y autenticación

**¿Aplica?** Sí.

| Evidencia | Estado |
|---|---|
| Login sin límite de intentos (`app/routes/auth.py`). | **Corregido:** rate limit por IP+email (10/min) y 429. |
| Contraseña mínima de 6 caracteres (`models.py:52-58`). | **Parcial:** se mantiene por compatibilidad de seeds/tests; recomendado subir a 12 en registro/reset. FIND-09. |
| Mensajes de login genéricos (`Invalid credentials`), cuenta desactivada, reset token de un solo uso lógico. | **Correcto**. |
| `get_current_user` lee rol de la BD, no confía solo en el claim del JWT. | **Correcto**. |
| Token de 24 h sin refresh/revocación. | **Aceptado (medio):** reducir TTL o añadir refresh es el siguiente paso. |
| Token en `localStorage` y query string del WS. | **Parcial** (FIND-19). |

---

## 9. A08 — Fallos de integridad de software y datos

**¿Aplica?** Sí.

| Evidencia | Estado |
|---|---|
| PDF RFP: cabecera `%PDF-`, tamaño máximo, nombre saneado, SHA-256 y escritura atómica. | **Correcto** (`app/services/rfp_service.py:89-110`). |
| CSV: validación de cabeceras/formatos y ahora límite de tamaño. | **Correcto**. |
| Seeds destructivos con `seed_guard.py` (`--force`, `--dry-run`, `--allow-remote-db`). | **Correcto**. |
| `npm ci` y lockfiles commiteados; `uv.lock` existe. | **Correcto**. |
| Imágenes Docker y `requirements.txt` sin digest/pins completos. | **Parcial** (FIND-15). |
| Sin CI que ejecute tests/evals/auditorías en cada PR. | **Pendiente:** no existe `.github/workflows`. FIND-27. |
| `markitdown` procesa PDFs no confiables en worker. | **Aceptado (bajo):** aislamiento en worker + límite de tamaño; recomendable sandbox/AV. |

---

## 10. A09 — Fallos de logging y monitorización

**¿Aplica?** Sí.

| Evidencia | Estado |
|---|---|
| Trazas por corrida con nodos, checkpoints, duración y fuentes; redacción de PII (`app/agent/tracing.py`). | **Correcto**. |
| Guardrails con contadores y endpoint `GET /agent/harness/stats` (`app/agent/harness/observability.py`). | **Correcto**. |
| Logs MCP JSON por tool call, argumentos saneados y sin tokens (`mcps/.../logs.py`). | **Correcto**. |
| Telemetría con envelope, allowlist, saneado, sampling, outbox y métricas de latencia/errores (`app/telemetry/`). | **Correcto**. |
| No hay eventos estructurados de login fallido/403/rate limit ni alertas. | **Parcial (FIND-16):** el rate limit ya corta el abuso, pero falta auditoría de auth y alertas. |
| `POST /telemetry/events` es público (pre-login) y no tiene auth. | **Aceptado (bajo):** rate limit 300/min + allowlist + saneado. FIND-20. |

---

## 11. A10 — Server-Side Request Forgery (SSRF)

**¿Aplica?** No en el flujo actual.

Evidencia:

- No hay URLs controladas por el usuario que se pasen a `httpx`, `requests` o
  `urlopen`.
- Los destinos salientes se leen de entorno: `LLM_BASE_URL` (`data/process/rag_config.py:65`),
  `QDRANT_URL`, `MCP_SERVER_URL` (`app/agent/tools/mcp_auth.py`), `TRACKFLOW_API_BASE_URL`
  (`mcps/.../settings.py:144`).
- El RAG no descarga URLs; indexa documentos locales de
  `docs/company-knowledge-base`.
- La telemetría no hace fetch de URLs.

**Riesgo residual (bajo):** si en el futuro se añade un “importar desde URL” o
se permite configurar `LLM_BASE_URL` desde el tenant, habrá que aplicar
allowlist de esquemas/hosts y bloquear IPs privadas.

---

## 12. Conclusión

- **A01, A02, A05 y A07** concentraban los riesgos críticos; están corregidos
  con tests de autorización, validación de configuración, rate limiting y
  hardening de red/contenedores.
- **A06** queda limpio en dependencias de producción y Python.
- **A09** tiene una base sólida de trazas/telemetría, pero falta auditoría de
  autenticación y alertas.
- **A10** no aplica hoy; queda documentado el requisito para futuras entradas
  de URL.
- Los riesgos aceptados (token en `localStorage`, CORS del MCP, tags de imagen,
  regex de inyección) están en el registro con su justificación y próximo paso.
