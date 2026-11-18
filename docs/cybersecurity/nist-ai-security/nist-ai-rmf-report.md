# Informe NIST AI RMF — TrackFlow Tech

**Fecha:** 2026-11-18  
**Autor:** Andrés Kim (CTO, TrackFlow Tech) — revisado por Thomas Harry (CEO)  
**Alcance:** todos los sistemas de IA del fork descritos en
[`ai-system-inventory.md`](./ai-system-inventory.md): agente CX, RAG,
MCP, memoria, chat en tiempo real, workflows RFP y APIs que tocan datos de
clientes.  
**Briefing:** [`docs/cybersecurity/nist-security-practices.md`](../nist-security-practices.md)  
**Evidencias:** [`evidence/`](./evidence/README.md)

---

## 1. Resumen ejecutivo

TrackFlow Tech ya opera un agente de soporte 24/7, un RAG sobre políticas y
SLAs, un servidor MCP OAuth y tres workflows de RFP con aprobación humana. La
compañía atiende datos B2C (contacto y direcciones) y B2B (volumen, incidencias
y condiciones contractuales) en **España (RGPD)** y **California
(CCPA/CPRA)**.

El control técnico base es sólido: el agente pasa por un harness determinista
(entrada, contenido externo, autorización de pedidos y salida), los endpoints
que invocan un modelo tienen rate limiting, las trazas se persisten y las
propuestas RFP requieren aprobación humana por departamento. Este ciclo ha
cerrado las brechas que quedaban en la frontera del **RAG comercial**, los
**endpoints RFP**, el **contenido de PDFs** y la **higiene de credenciales de
desarrollo**.

Las brechas restantes son de **gobierno y operación** (DPA/DPIA formales,
presupuesto de coste por usuario, CI de evaluaciones, alertas persistentes y un
SLA interno de respuesta), no de explotabilidad inmediata. Están priorizadas y
con responsable en la §5.

**Acción más urgente (P0):** formalizar el registro de encargados y firmar el
DPA con el proveedor del modelo y la base de datos antes de procesar datos de
producción, y publicar el procedimiento de notificación a la AEPD en 72 h.

---

## 2. Marco regulatorio aplicable

El briefing fija el marco; este informe se limita a él y no inventa normativa.

### 2.1 España / Unión Europea — RGPD

| Obligación | Aplicación en TrackFlow | Estado |
|---|---|---|
| **Art. 5** minimización y limitación de finalidad | El agente solo recibe el mensaje y el contexto necesario; la memoria exige aprobación y se filtra por rol | Implementado |
| **Art. 28** contrato de encargado del tratamiento | LLM proxy/OpenRouter/DeepSeek/Perplexity, Supabase, Auth0 y Resend son encargados; Qdrant es self-hosted | **Pendiente** (NIST-14) |
| **Art. 30** registro de actividades | Inventario de sistemas y flujos de datos | Parcial (este documento) |
| **Art. 32** seguridad del tratamiento | Harness, rate limiting, scopes, secretos por entorno, hardening | Implementado |
| **Art. 33** notificación a la **AEPD en 72 horas** | Runbook de incidentes con decisión de notificación en 48 h | **Propuesto** (NIST-13) |
| **Art. 34** comunicación a interesados si hay alto riesgo | Plantilla de comunicación y criterio de activación | **Propuesto** (NIST-13) |
| **Art. 35** evaluación de impacto (DPIA) | Necesaria para el agente CX y para el futuro motor de devoluciones | **Pendiente** (NIST-14) |
| **Arts. 44 y ss.** transferencias internacionales | Proveedores en EE. UU.; requiere SCC o decisión de adecuación (EU-US DPF) | **Pendiente** (NIST-14) |

### 2.2 California — CCPA/CPRA

| Derecho / obligación | Aplicación en TrackFlow | Estado |
|---|---|---|
| Aviso en la recogida (notice at collection) | El portal B2C debe informar de la finalidad y categorías | Parcial (texto legal fuera de este repo) |
| Derechos de acceso, eliminación, corrección y opt-out | La eliminación de memoria y datos de cliente existe como operación de manager; falta un flujo B2C formalizado | Parcial |
| Contratos de proveedor de servicio | Mismos encargados que en RGPD | **Pendiente** (NIST-14) |
| Seguridad razonable | Controles de la §3 | Implementado |
| Notificación de brecha "without unreasonable delay" (Cal. Civ. Code §1798.82) y al Fiscal General si afecta a >500 residentes en California | Runbook común con el de RGPD | **Propuesto** (NIST-13) |

### 2.3 Datos restringidos y decisiones automatizadas

- **Alta sensibilidad:** nombre, dirección, teléfono y email de los
  destinatarios B2C; volumen, incidencias y condiciones contractuales de las
  marcas B2B.
- **Crítico:** credenciales de integración (LLM, Qdrant, Supabase, Auth0,
  Resend) y tokens JWT.
- **No hay decisiones automatizadas con efectos jurídicos (art. 22 RGPD):** las
  propuestas RFP se aprueban por una persona nombrada y el documento final solo
  se emite tras el `final_gate`. El futuro motor de devoluciones deberá mantener
  esa regla por encima del umbral económico que defina Sofía Ramos.

---

## 3. Inventario y mapa de entradas

- Inventario completo con responsable de negocio, responsable técnico,
  proveedor y control de terceros: [`ai-system-inventory.md`](./ai-system-inventory.md).
- Mapa de los 14 puntos donde un modelo recibe input externo (usuario,
  documento, tool MCP, memoria, otro LLM): [`README.md`](./README.md) §1.

Resumen de responsables: Valentina Cruz (CX), Carlos Vega (última milla),
Sofía Ramos (logística inversa), Miguel Torres (comercial), Ana Whitfield
(operaciones), Andrés Kim (tecnología) y Thomas Harry (dirección).

---

## 4. Las seis funciones NIST

Leyenda de prioridad: **P0** = antes de producción o de exponer datos reales;
**P1** = siguiente ciclo; **P2** = mejora continua.

### 4.1 GOVERN — gobernar

**Objetivo:** que cada sistema de IA tenga dueño, política y límite de actuación
antes de operar.

| # | Acción | Prioridad | Responsable | Evidencia |
|---|---|---|---|---|
| G1 | Publicar el inventario con RACI y proveedor por componente | **P0** | Andrés Kim | `ai-system-inventory.md` |
| G2 | Política de uso aceptable: qué puede decidir un agente y qué exige humano | **P0** | Thomas Harry / Andrés Kim | §4.6 y `data/pipelines/rfp_approval/` |
| G3 | Registro de terceros y DPA/DPIA por proveedor de modelo y datos | **P0** | Andrés Kim / asesoría legal | NIST-14 (pendiente) |
| G4 | Clasificación de datos y regla de "no mezclar marcas B2B" | **P0** | Andrés Kim | `ai-system-inventory.md` §4; `app/agent/rag_policy.py` |
| G5 | Change management: cambio de modelo/proveedor = cambio de configuración validado con evals | **P1** | Andrés Kim | `tests/pipelines/test_agent_evals.py` |
| G6 | Formación anual del equipo de CX y operaciones sobre uso seguro del agente | **P2** | Valentina Cruz / Andrés Kim | — |

### 4.2 IDENTIFY — identificar

**Objetivo:** conocer superficies de ataque, datos y dependencias.

| # | Acción | Prioridad | Responsable | Evidencia |
|---|---|---|---|---|
| I1 | Threat model por componente (inyección, fuga, excessive agency) | **P0** | Andrés Kim | `README.md` §1 + este informe |
| I2 | Inventario de entradas externas al modelo (14 puntos) | **P0** | Andrés Kim | `README.md` §1.2 |
| I3 | Inventario de tools y scopes MCP (6 tools, lectura/escritura) | **P1** | Andrés Kim | `mcps/trackflow-mcp/README.md`; `app/agent/tools/mcp_auth.py` |
| I4 | Corpus de evaluación de inyección y de dominio | **P1** | Andrés Kim | `services/api/tests/fixtures/harness_corpus.json` |
| I5 | Escaneo de dependencias (`pip-audit`, `npm audit`) en cada release | **P1** | Andrés Kim | `docs/cybersecurity/evidence/10-fixes/pip-audit.txt` |
| I6 | Inventario de sistemas planificados (carrier, devoluciones, visión) antes de construirlos | **P2** | Responsables de área | `ai-system-inventory.md` §1 |

### 4.3 PROTECT — proteger

**Objetivo:** que ninguna entrada externa pueda cambiar las reglas ni sacar
datos de otra sesión.

| # | Acción | Prioridad | Responsable | Evidencia |
|---|---|---|---|---|
| P1 | Jerarquía explícita de instrucciones (system > usuario > contexto > tool > memoria) | **P0** | Andrés Kim | `app/agent/harness/prompt.py` |
| P2 | Screening de entrada (inyección, control chars, longitud, alcance, pedido ajeno) | **P0** | Andrés Kim | `app/agent/harness/runtime.py:187`; `prompt-injection-tests.md` |
| P3 | Aislamiento de RAG y tools (`<untrusted_content>`, neutralización) | **P0** | Andrés Kim | `app/agent/harness/external.py:57,142` |
| P4 | Saneado de documentos RFP y del comentario humano antes de cualquier prompt | **P0** | Andrés Kim | `data/pipelines/rfp_intake/sanitize.py`; `data/pipelines/rfp_approval/approval_graph.py`; 10 tests |
| P5 | Validación de salida (fuga de prompt, PII, tarifas, pedido ajeno, política país) | **P0** | Andrés Kim | `app/agent/harness/output.py:232` |
| P6 | Mínimo privilegio: roles y scopes (`user`/`manager`/`admin`; `mcp:read` sin `mcp:write` para el agente) | **P0** | Andrés Kim | `app/agent/tools/mcp_auth.py:50`; `test_security_hardening.py` |
| P7 | Rate limiting en todos los endpoints que invocan un modelo | **P0** | Andrés Kim | `app/core/rate_limit.py`; `evidence/rate-limit.txt` |
| P8 | Secretos solo por entorno, `.env` 600, fail-fast en producción | **P0** | Andrés Kim | `app/core/config.py`; `evidence/secret-scan.txt` |
| P9 | Tres workflows con confirmación humana (RFP, memoria, interrupción del chat) | **P0** | Andrés Kim | `data/pipelines/rfp_approval/approval_graph.py:97`; `evidence/human-approval.txt` |
| P10 | Validación del output estructurado de agentes que generan datos (contratos Pydantic + guardarraíl numérico) | **P1** | Andrés Kim | `data/pipelines/rfp_proposal/`; `service/api/app/agent/tools/contracts.py` |
| P11 | Validación de llamadas a tools antes de ejecutarlas: firma tipada en FastMCP, scopes OAuth y guards; el agente nunca genera SQL ni código | **P0** | Andrés Kim | `mcps/trackflow-mcp/trackflow_mcp/tools/guards.py`; `app/agent/tools/mcp_auth.py` |

### 4.4 DETECT — detectar

**Objetivo:** saber cuándo alguien intenta abusar del sistema y qué decidió el
agente.

| # | Acción | Prioridad | Responsable | Evidencia |
|---|---|---|---|---|
| D1 | Eventos de guardrail con categoría, motivo, `run_id`, snippet redactado y hash de la pregunta | **P0** | Andrés Kim | `app/agent/harness/observability.py` |
| D2 | Traza por corrida: nodos, ruta, fuentes, tools, checkpoints y duración | **P0** | Andrés Kim | `app/agent/tracing.py`; `evidence/agent-trace.json` |
| D3 | Endpoint manager para consultar trazas por `run_id` | **P1** | Andrés Kim | `GET /agent/traces/{run_id}` (nuevo) |
| D4 | Contadores por guard y sesión (`GET /agent/harness/stats`) | **P1** | Andrés Kim | `app/routes/agent_harness.py` |
| D5 | Alertas sobre picos de 429, bloqueos de inyección y fallos de tool | **P1** | Andrés Kim | **Pendiente** (NIST-12) |
| D6 | Persistencia y retención de eventos de guardrail fuera del proceso | **P1** | Andrés Kim | **Pendiente** (NIST-12) |
| D7 | CI que ejecute tests, evals y auditorías en cada PR | **P1** | Andrés Kim | **Pendiente** (NIST-15) |

### 4.5 RESPOND — responder

**Objetivo:** contener un incidente y cumplir los plazos legales.

> **SLA del briefing:** el único plazo explícito es la **notificación a la AEPD
> en 72 horas** (RGPD) y la notificación "sin demora injustificada" de CCPA. El
> briefing **no define un SLA interno**, por lo que se propone y se marca como
> brecha (NIST-13).

| # | Acción | Prioridad | Responsable | Plazo propuesto |
|---|---|---|---|---|
| R1 | Runbook de incidente de IA: detección, severidad, contención, evidencia, notificación | **P0** | Andrés Kim | — |
| R2 | Contención inmediata: revocar `LLM_API_KEY`/`QDRANT_API_KEY`, desactivar el agente, invalidar sesiones | **P0** | Andrés Kim | ≤ 1 h desde la confirmación |
| R3 | Preservar trazas y eventos de guardrail antes de reiniciar | **P0** | Andrés Kim | ≤ 2 h |
| R4 | Decisión de notificación a la **AEPD** y comunicación a interesados | **P0** | Andrés Kim / legal | dentro de 72 h |
| R5 | Notificación CCPA y al Fiscal General de California si >500 residentes | **P1** | Andrés Kim / legal | "sin demora injustificada" |
| R6 | Revisión post-incidente con acciones y dueño | **P2** | Andrés Kim | ≤ 5 días |

**Escalado:** Andrés Kim → Thomas Harry → asesoría legal/DPO. Un intento de
inyección bloqueado es un evento de seguridad, no un incidente; se revisa en el
informe semanal salvo que haya éxito confirmado.

### 4.6 RECOVER — recuperar

**Objetivo:** volver a operar sin repetir el fallo.

| # | Acción | Prioridad | Responsable | Evidencia |
|---|---|---|---|---|
| C1 | Backups de Supabase y del volumen de Qdrant; artefactos RFP en `data/raw/rfp` | **P0** | Andrés Kim | `docker-compose.yml` (volúmenes) |
| C2 | Restauración probada y documentada (RTO/RPO a definir con negocio) | **P1** | Andrés Kim | **Pendiente** (NIST-16) |
| C3 | Reproducir una propuesta desde el handoff sin reparsear el PDF | **P1** | Andrés Kim | `scripts/rfp_reprocess.py`; `POST /rfp/tickets/{id}/proposal` |
| C4 | Rotación de credenciales y scopes tras una fuga | **P0** | Andrés Kim | `scripts/security/check-secret-permissions.sh` |
| C5 | Failover de modelo/proveedor cambiando `GENERATION_MODEL`/`LLM_BASE_URL` | **P1** | Andrés Kim | `services/api/.env.example` |
| C6 | Invalidar caché y reindexar la KB si un documento se compromete | **P1** | Andrés Kim | `app/core/cache.py`; `data/process/rag_index.py` |

---

## 5. Registro de brechas

Estados: **Corregido** en este ciclo · **Parcial** · **Pendiente** ·
**Aceptado** (riesgo documentado).

| ID | Función | Brecha | Riesgo | Impacto regulatorio | Mitigación / estado | Responsable |
|---|---|---|---|---|---|---|
| NIST-01 | Protect | `POST /knowledge/query` invocaba al modelo sin screening, sin aislar el contexto y sin rate limit | Inyección directa/indirecta en el asistente comercial; coste descontrolado | RGPD art. 32 | **Corregido:** screening + `isolate_context` + 30/min + tests | Andrés Kim |
| NIST-02 | Protect | Endpoints RFP (subida, propuesta, aprobaciones) sin rate limit | Bucle de coste con una cuenta manager comprometida | RGPD art. 32 | **Corregido:** 10/5/20 por minuto + tests | Andrés Kim |
| NIST-03 | Protect | PDFs RFP y comentarios de aprobación entraban a los prompts sin neutralizar instrucciones | Inyección indirecta: alterar la propuesta, saltarse reglas de precio o aprobación | RGPD art. 32; integridad contractual | **Corregido:** `sanitize_document_text` en intake y en la regeneración + regla "documento = datos" + tests | Andrés Kim |
| NIST-04 | Protect | `.env.example` del MCP traía `TRACKFLOW_API_PASSWORD=admin123` | Credencial conocida en un servicio con rol manager | RGPD art. 32 | **Corregido:** password vacía + cuenta `mcp-service` | Andrés Kim |
| NIST-05 | Protect | Contraseñas de desarrollo literales en seeders y scripts | Reutilización en entornos compartidos | RGPD art. 32 | **Corregido:** `SEED_*` o generación aleatoria impresa una vez | Andrés Kim |
| NIST-06 | Protect | WebSocket de chat sin límite por mensaje | Bucle de coste y abuso de sesión | RGPD art. 32 | **Corregido:** `CHAT_WS_MESSAGE_LIMIT` (30/min) + test | Andrés Kim |
| NIST-07 | Detect | No había forma de consultar una traza del agente CX por API | Difícil reconstruir por qué el agente actuó | RGPD art. 32 | **Corregido:** `GET /agent/traces/{run_id}` (manager) | Andrés Kim |
| NIST-08 | Identify | Los motores de carrier y de aprobación de devoluciones **no existen** en este fork | No auditable hoy; alto impacto si se construyen sin gates | RGPD art. 22 si decidieran sobre personas | **Pendiente (N/A hoy):** diseñar con `interrupt` humano y umbral; dueños Carlos Vega y Sofía Ramos | Andrés Kim |
| NIST-09 | Protect | Sin presupuesto de tokens/coste por usuario o modelo | Coste ilimitado ante abuso o bucle | — | **Pendiente:** cuota por usuario y alerta de gasto; el rate limit es la contención actual | Andrés Kim |
| NIST-10 | Detect | Detección de inyección por regex es evitable con paráfrasis | Un ataque nuevo podría pasar el filtro | RGPD art. 32 | **Aceptado:** defensa en profundidad (autorización, output guard, ACL, humano). Revisión trimestral del corpus | Andrés Kim |
| NIST-11 | Protect | El handoff RFP (salida de otro LLM) no se sanea como un documento externo | Propagación de una instrucción entre agentes | Integridad contractual | **Parcial:** contratos Pydantic, guardarraíl numérico, revisión humana y rule "payload = datos" | Andrés Kim |
| NIST-12 | Detect | Eventos de guardrail en memoria + log; sin alertas ni retención | Un pico de ataques pasa desapercibido tras reiniciar | RGPD art. 32 | **Pendiente:** sink JSONL/observabilidad + alertas sobre `by_guard` y 429 | Andrés Kim |
| NIST-13 | Respond | El briefing no define SLA interno de respuesta; solo las 72 h de la AEPD | Notificación tardía o caótica | RGPD arts. 33/34; CCPA §1798.82 | **Pendiente:** publicar runbook con 1 h contención / 48 h decisión / 72 h AEPD | Andrés Kim / Thomas Harry |
| NIST-14 | Govern | Sin DPA/DPIA firmados ni registro formal de transferencias internacionales | Tratamiento sin base contractual con encargados | RGPD arts. 28, 35, 44 | **Pendiente:** registro de encargados + DPA + DPIA del agente CX | Andrés Kim / legal |
| NIST-15 | Detect | Sin CI que ejecute tests, evals y auditorías | Regresión silenciosa de guardrails | — | **Pendiente:** workflow de PR con pytest, evals y `pip-audit`/`npm audit` | Andrés Kim |
| NIST-16 | Recover | Sin restauración probada ni RTO/RPO acordados | Pérdida de datos o parada prolongada | RGPD art. 32 | **Pendiente:** simulacro trimestral y RTO/RPO firmados | Andrés Kim |
| NIST-17 | Protect | JWT en `localStorage` y en query string del WebSocket | Robo de sesión si hay XSS o logs de proxy | RGPD art. 32 | **Aceptado:** CSP, sin XSS conocido; migrar a cookie httpOnly y auth por primer frame | Andrés Kim |
| NIST-18 | Govern | El MCP usa una cuenta de servicio con rol `manager`, sin rol específico | Exceso de privilegio si la cuenta se compromete | RGPD art. 32 | **Parcial:** scopes `mcp:read` para el agente y tools de inventario solo lectura | Andrés Kim |
| NIST-19 | Govern | Sin vault externo; el secreto vive en `.env` del host | Rotación manual y dependencia de permisos del host | RGPD art. 32 | **Aceptado (dev):** `.env` 600 + fail-fast; en producción inyectar por el orquestador o vault | Andrés Kim |

---

## 6. Acciones irreversibles y confirmación humana

El briefing (§5) fija cuatro acciones que exigen confirmación humana. Este es
el estado real en el fork:

| Acción del briefing | ¿Existe en el fork? | Control actual | Evidencia |
|---|---|---|---|
| Aprobar una devolución por encima de un umbral | **No** (motor planificado) | Se documenta el requisito para cuando se construya: `interrupt()` + aprobador nombrado + umbral de Sofía Ramos | `ai-system-inventory.md` AI-16; NIST-08 |
| Confirmar el despacho de un envío de alto valor sin validación adicional | **No** (no hay endpoint de despacho) | El despacho no lo ejecuta ningún agente; el inventario solo registra entrada/salida con rol manager | `app/routes/inventory.py` |
| Cambiar el carrier de un envío en tránsito | **No** (motor planificado) | Se exigirá aprobación humana y motivo; hoy no hay herramienta que lo permita | `ai-system-inventory.md` AI-15; NIST-08 |
| Compartir datos de volumen/incidencias de una marca B2B con otra | **Sí (riesgo)** | Bloqueado por ACL: RAG filtra documentos internos, inventario y memoria filtran por rol, y el agente no puede asociar `client_id` ajeno | `test_security_hardening.py`; `app/agent/rag_policy.py` |

**Acciones irreversibles que sí existen y sí exigen humano:**

1. **Emitir el documento final de una propuesta RFP.** El grafo se detiene en
   `interrupt()` por departamento (`approval_graph.py:97`); la decisión exige
   aprobador nombrado, comentario en `reject`/`request_changes` y
   `acknowledge_provisional` si la sección es provisional. Sin todas las
   aprobaciones no hay `final_gate` ni `rfp-final-v1`.
   Evidencia: `scripts/rfp_e2e.py` y `evidence/human-approval.txt`.
2. **Persistir un hecho en la memoria del agente.** Se propone, se valida y
   solo se escribe tras una decisión humana (`POST /agent/memory/proposals/...`);
   una decisión no relacionada rechaza por defecto.
3. **Borrar usuarios o proveedores.** Requiere rol admin/manager y la UI pide
   confirmación explícita antes de la llamada.

**Brecha operativa:** la confirmación de las acciones de la UI (por ejemplo, una
salida de inventario) es una confirmación de cliente, no un token de
confirmación emitido por el servidor. Se acepta para este ciclo porque la
operación exige un manager autenticado; si el negocio la considera
irreversible, debe añadirse un `confirmation_token` de un solo uso (NIST-08).

---

## 7. Evidencias

| Evidencia | Archivo |
|---|---|
| Escaneo de secretos, permisos y ejemplos | [`evidence/secret-scan.txt`](./evidence/secret-scan.txt) |
| Corpus del harness (input/output) | [`evidence/harness-demo.txt`](./evidence/harness-demo.txt) |
| Prompt injection directa e indirecta | [`evidence/injection-demo.txt`](./evidence/injection-demo.txt) |
| Traza del agente | [`evidence/agent-trace.json`](./evidence/agent-trace.json) |
| Rate limiting | [`evidence/rate-limit.txt`](./evidence/rate-limit.txt) |
| Aprobación humana RFP | [`evidence/human-approval.txt`](./evidence/human-approval.txt) |
| Suites y typecheck | [`evidence/test-results.txt`](./evidence/test-results.txt) |

---

## 8. Conclusión

TrackFlow puede operar el agente CX y los workflows RFP con un nivel de
seguridad razonable para datos reales **si** se cierran las brechas P0 de
gobierno (NIST-13 y NIST-14) antes de conectar datos de producción. El control
técnico está probado y es reproducible; lo que falta es el contrato con los
terceros, el procedimiento de incidentes con plazos y la automatización de
detección.

**Firmas pendientes de sign-off:**

- Andrés Kim — CTO, responsable técnico del inventario y los controles.
- Thomas Harry — CEO, aprueba el registro de brechas y el presupuesto de
  mitigación.
- Valentina Cruz — CX, aprueba el alcance del agente y la política de escalado.
