# Registro de hallazgos — Auditoría OWASP / hardening

**Fecha:** 2026-11-17  
**Rama:** `feature/owasp-top10-audit`

Estados: `Corregido` (fix + test/evidencia), `Mitigado` (control compensatorio),
`Parcial` (parte del riesgo cubierto), `Aceptado` (riesgo documentado),
`N/A` (no aplica), `Pendiente` (requiere operación/CI).

| ID | Categoría | Sev. | Hallazgo | Evidencia | Corrección | Verificación | Estado |
|---|---|---|---|---|---|---|---|
| FIND-01 | A01 | Crítica | `GET /telemetry/report` sin autenticación | `app/routes/telemetry.py:122` (antes) | `require_manager` y rate limit | `authz-matrix.md`: anónimo 401, `user` 403 | Corregido |
| FIND-02 | A01 | Crítica | Inventario accesible a rol `user`; expone `client_id` de todas las marcas | `app/routes/inventory.py:39,57`, `app/agent/tools/contracts.py:122-133` | `require_manager` en REST + gate de rol en tool del agente | `test_security_hardening.py`, `authz-matrix.md` | Corregido |
| FIND-03 | A01 | Crítica | `GET /agent/memory` global para cualquier autenticado; `client_preference` se inyectaba a todos | `app/routes/agent_memory.py:151`, `app/agent/memory/store.py:637` | `require_manager` + filtro de tipos de memoria por rol | `test_agent_chat.py`, tests de memoria | Corregido |
| FIND-04 | A01 | Crítica | RAG comercial (precios/descuentos) accesible a rol `user` y al agente CX | `data/pipelines/rag.py:14-27`, `app/routes/knowledge.py:38`, `data/process/rag_index.py:88-104` | `app/agent/rag_policy.py`: audiencia pública vs interna; `/knowledge/query` manager | `test_security_hardening.py::test_rag_filter_*` | Corregido |
| FIND-05 | A02 | Crítica | `SECRET_KEY` efímera si falta; placeholder en ejemplo | `app/core/security.py:14-16`, `.env.example:10` | `validate_security_config()` falla en producción | `test_production_rejects_weak_secret` | Corregido |
| FIND-06 | A02 | Crítica | Credenciales por defecto (`admin123`) en ejemplos y `.env` legibles por terceros | `.env.example:100-102`, `mcps/.../.env.example:29-30`; `stat` 644 | Ejemplos sin secretos, cuenta `mcp-service`, `.env` a `600`, script de comprobación | `secret-permissions.txt`, `pip-audit` | Corregido (rotación real = ops) |
| FIND-07 | A05 | Crítica | Redis/Qdrant/Flower/MCP/Prefect publicados en `0.0.0.0`; Docker se salta UFW | `docker-compose.yml` (puertos), `docker ps` inicial | Bind a `127.0.0.1`, Redis sin publicar, overlay hardened, reglas `DOCKER-USER` | `docker-ports-and-users.txt`, `hardening-config.txt` | Corregido en repo; verificación en host pendiente |
| FIND-08 | A06 | Crítica | `python-jose`/`ecdsa` vulnerables; Next/PostCSS/sharp críticos | `pip-audit` baseline, `npm audit` baseline | `PyJWT`, Next `16.4.6`, `npm audit fix` | `pip-audit.txt`, `npm-audit-*.json` (0 prod) | Corregido |
| FIND-09 | A07 | Alta | Login sin rate limit; contraseña mínima 6 | `app/routes/auth.py`, `models.py:52-58` | `app/core/rate_limit.py` (login 10/min, forgot/reset, agente, telemetría) | `test_login_rate_limit_returns_429` | Corregido (política de longitud = parcial) |
| FIND-10 | A01 | Alta | Registro público permite obtener cuenta `role=user` | `app/routes/users.py:19` | `ALLOW_PUBLIC_REGISTRATION=false` por defecto en producción | `test_public_registration_disabled_in_production` | Mitigado |
| FIND-11 | A05 | Alta | `ALLOWED_ORIGINS` hardcodeado; ignoraba la env | `app/main.py:56` (antes) | `allowed_origins()` desde entorno, rechaza `*` | `test_allowed_origins_rejects_wildcard` | Corregido |
| FIND-12 | A05 | Alta | Contenedores root; `--reload` en producción | `services/Dockerfile`, `uis/Dockerfile` | `USER appuser` / `USER node`; overlay hardened sin reload | `docker compose exec id`, `hardening-config.txt` | Corregido |
| FIND-13 | A05 | Alta | MCP `MCP_CORS_ORIGINS=*` por defecto | `mcps/.../settings.py:140` | `.env.example` raíz explícito; default de código sigue `*` (carpeta protegida) | Revisión manual | Parcial |
| FIND-14 | A05 | Alta | Sin cabeceras de seguridad en frontends | `uis/*/next.config.ts` | CSP + `nosniff` + `XFO` + `Referrer-Policy` + `Permissions-Policy` | `security-headers.txt` | Corregido |
| FIND-15 | A08 | Alta | `requirements.txt` sin pins; imágenes con tags flotantes | `services/api/requirements.txt`, Dockerfiles | `PyJWT` fijado; pendiente pins/digests completos | `pip-audit`, revisión | Parcial |
| FIND-16 | A09 | Alta | Sin eventos estructurados de login fallido/403/rate limit ni alertas | `app/routes/auth.py` | Rate limit ya corta abuso; falta auditoría/alerting | Revisión + tests | Parcial |
| FIND-17 | A01 | Alta | `client_id` del chat aceptado sin verificar pertenencia | `app/routes/chat.py:56` | 403 para `user`; solo manager/admin asocia marca | `test_chat_client_id_*` | Corregido |
| FIND-18 | A03 | Media | CSV de incidencias sin límite de tamaño | `app/routes/incidents.py:75` | `INCIDENT_MAX_UPLOAD_MB=10`, respuesta 413 | Tests de API | Corregido |
| FIND-19 | A02/A07 | Media | JWT en `localStorage` y en query string del WebSocket | `AuthContext.tsx:42-50`, `lib/chat-socket.ts:59-75` | CSP y sin XSS; recomendado cookie httpOnly + auth por primer frame | Revisión manual | Aceptado |
| FIND-20 | A09 | Baja | `POST /telemetry/events` público (pre-login) | `app/routes/telemetry.py:53` | Rate limit 300/min + allowlist + saneado | `test_telemetry_barriers.py` | Aceptado |
| FIND-21 | A05 | Media | `/docs` y `/openapi.json` expuestos | `app/main.py:86-88` | Deshabilitados en producción | Revisión de código | Corregido |
| FIND-22 | A10 | N/A | SSRF | Sin URLs de usuario a `httpx/requests/urlopen`; destinos por env | Documentado en auditoría §11 | Grep + revisión | N/A |
| FIND-23 | A04 | N/A | Motores de devoluciones/carriers sin confirmación humana | No existen como endpoints separados en este fork | Flujo RFP sí tiene `interrupt()` humano | `data/pipelines/rfp_approval/` | N/A |
| FIND-24 | A01/A05 | Media | MCP usa cuenta de servicio `manager`; no hay rol `mcp` específico | `mcps/.../backend.py`, `seed_mcp_service.py` | Agente filtra `mcp:write`; tools de inventario solo lectura | `test_agent_mcp_scopes_are_read_only` | Parcial |
| FIND-25 | A03 | Media | Detección de prompt injection por regex es evitable | `app/agent/harness/injection.py` | Defensa en profundidad: autorización, external guard, output guard | Corpus de harness | Aceptado |
| FIND-26 | A04 | Media | Sin presupuesto/cuota de coste por usuario/modelo | No implementado | Recomendado límite de tokens/coste por sesión | Revisión | Pendiente |
| FIND-27 | A08 | Media | Sin CI que ejecute tests/evals/auditorías | No `.github/workflows` | Recomendado pipeline de PR | Revisión | Pendiente |

---

## Evidencia reproducible

| Evidencia | Ruta |
|---|---|
| Matriz de autorización antes | `docs/cybersecurity/evidence/00-baseline/authz-matrix.md` |
| Matriz de autorización después | `docs/cybersecurity/evidence/10-fixes/authz-matrix.md` |
| Puertos y usuarios Docker después | `docs/cybersecurity/evidence/10-fixes/docker-ports-and-users.txt` |
| Configuración de hardening validada | `docs/cybersecurity/evidence/10-fixes/hardening-config.txt` |
| Permisos de `.env` | `docs/cybersecurity/evidence/10-fixes/secret-permissions.txt` |
| Cabeceras HTTP | `docs/cybersecurity/evidence/10-fixes/security-headers.txt` |
| `pip-audit` antes/después | `evidence/00-baseline/pip-audit.txt`, `evidence/10-fixes/pip-audit.txt` |
| `npm audit` producción | `evidence/10-fixes/npm-audit-backoffice.json`, `...website.json` |
| Tests backend | `services/api/tests/test_security_hardening.py` (23 casos) |

## Comandos para regenerar

```bash
# API
cd services/api && source venv/bin/activate && pytest -q

# Frontends
cd uis/backoffice && npm run lint && npm test && npm run build
cd uis/website && npm run lint && npm run build

# Autorización
python ../../scripts/security/authz_matrix.py

# Dependencias
pip-audit -r requirements.txt
npm audit --omit=dev --prefix ../../uis/backoffice
npm audit --omit=dev --prefix ../../uis/website

# Hardening
bash scripts/security/hardening/test-hardening.sh
bash scripts/security/check-secret-permissions.sh
```

---

## Ciclo NIST AI Security (2026-11-18)

El ciclo posterior de seguridad de IA no duplica este registro: sus brechas
viven en
[`nist-ai-security/nist-ai-rmf-report.md`](./nist-ai-security/nist-ai-rmf-report.md) §5
(`NIST-01` … `NIST-19`), con la acción, el responsable y la mitigación.

Correcciones de este ciclo que tocan hallazgos previos:

- **FIND-06:** el `.env.example` del MCP ya no incluye `admin123`; los seeders
  y scripts de desarrollo tampoco contienen contraseñas literales.
- **FIND-09 / FIND-16:** se añaden rate limits a `/knowledge/query`, a los
  endpoints RFP, al WebSocket de chat y una API de consulta de trazas
  (`GET /agent/traces/{run_id}`).
- **FIND-25:** la inyección indirecta de PDFs RFP se mitiga ahora con
  `data/pipelines/rfp_intake/sanitize.py` y una regla explícita en los prompts.
