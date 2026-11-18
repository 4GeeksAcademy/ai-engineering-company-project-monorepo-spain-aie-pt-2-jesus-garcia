# Inventario de sistemas de IA — TrackFlow

**Fecha:** 2026-11-17  
**Alcance:** todo lo construido en el fork de TrackFlow Tech (agentes, RAG,
MCP, workflows, modelos y APIs que tocan datos de clientes) más los sistemas
planificados que ya tienen responsable asignado.

Leyenda de estado: **Implementado** · **Parcial** · **Planificado** (no
construido todavía; se incluye para que el responsable y el control queden
asignados antes de escribirlo).

---

## 1. Inventario

| ID | Componente | Qué hace | Estado | Responsable de negocio | Responsable técnico | Modelo / herramienta | Proveedor | Clasificación de datos |
|---|---|---|---|---|---|---|---|---|
| AI-01 | Agente CX 24/7 (LangGraph) | Resuelve consultas de tracking, devoluciones e incidencias con RAG + tools | Implementado | Valentina Cruz (CX) | Andrés Kim (CTO) | `deepseek-v4-flash` (generación), `pplx-embed-v1-0.6b` (embeddings) | 4Geeks LiteLLM → OpenRouter / Perplexity | B2C: contacto y direcciones · B2B: volumen e incidencias |
| AI-02 | Harness de guardrails | Screening de entrada, autorización de pedidos, aislamiento de contenido externo, validación de salida, observabilidad | Implementado | Valentina Cruz | Andrés Kim | Sin modelo (reglas deterministas) | Interno | Metadatos de conversación (redactados) |
| AI-03 | Memoria del agente | Propone, valida y persiste hechos de conversación con aprobación humana | Implementado | Valentina Cruz | Andrés Kim | `deepseek-v4-flash` | 4Geeks LiteLLM → OpenRouter | Preferencias operativas B2B/B2C, PII redactada |
| AI-04 | Chat en tiempo real (REST + WebSocket) | Streaming de respuestas, interrupción y rehidratación por sesión | Implementado | Valentina Cruz | Andrés Kim | Hereda AI-01 | 4Geeks LiteLLM → OpenRouter | Conversaciones B2C/B2B |
| AI-05 | Base de conocimiento semántica (RAG) | Indexa políticas de SLA, devoluciones, precios y cobertura de carriers | Implementado | Valentina Cruz · Sofía Ramos (devoluciones) · Miguel Torres (comercial) | Andrés Kim | `pplx-embed-v1-0.6b` + Qdrant | OpenRouter / Perplexity · Qdrant self-hosted | Documentos internos y comerciales |
| AI-06 | Asistente comercial `/knowledge/query` | Responde a account managers sobre tarifas y políticas publicadas | Implementado | Miguel Torres (Comercial) | Andrés Kim | `deepseek-v4-flash` | 4Geeks LiteLLM → OpenRouter | Tarifas publicadas y condiciones B2B |
| AI-07 | Servidor MCP (`trackflow-mcp`) | Expone tools de incidencias e inventario a agentes vía OAuth 2.1 | Implementado | Andrés Kim | Andrés Kim | Sin modelo propio (tools deterministas) | Auth0 (identidad) · API TrackFlow | Incidencias, stock, `client_id` |
| AI-08 | Recepción de RFPs (Parte 1) | Convierte PDF, clasifica, extrae metadatos y reparte por departamento | Implementado | Miguel Torres | Andrés Kim | `deepseek-v4-flash` + MarkItDown | 4Geeks LiteLLM → OpenRouter · MarkItDown (OSS) | Documentos de clientes B2B (confidenciales por contrato) |
| AI-09 | Generación y evaluación de propuestas (Parte 2) | Redacta secciones por departamento y las evalúa (legibilidad, pertinencia, compliance) | Implementado | Miguel Torres · Sofía Ramos · Ana Whitfield | Andrés Kim | `deepseek-v4-flash` + tarifa determinista | 4Geeks LiteLLM → OpenRouter | Precios, capacidad y compromisos contractuales |
| AI-10 | Aprobación humana y cierre (Parte 3) | Interrumpe por departamento, arbitra conflictos y emite el documento final | Implementado | Miguel Torres · Sofía Ramos | Andrés Kim | Sin modelo (grafo con `interrupt`) | Interno | Documento final B2B |
| AI-11 | API de inventario unificada | Stock por SKU y almacén, órdenes de entrada/salida | Implementado | Ana Whitfield (Operaciones) | Andrés Kim | Sin modelo | Supabase (PostgreSQL) | Stock por marca (`client_id`) |
| AI-12 | Gestor y analizador de incidencias | CRUD de incidencias y análisis de CSV de satisfacción | Implementado | Valentina Cruz · Carlos Vega | Andrés Kim | Sin LLM (pandas + reglas) | Interno | Tickets de clientes (PII) |
| AI-13 | Telemetría y notificaciones SSE | Captura de eventos, barreras de privacidad y alertas SLA en tiempo real | Implementado | Andrés Kim | Andrés Kim | Sin modelo | Redis / SSE | Eventos de producto (sin PII) |
| AI-14 | Modelo de previsión de ventas | Regresión temporal para planificación comercial | Implementado | Miguel Torres · Thomas Harry | Andrés Kim | Scikit-learn (regresión) | Interno | Series agregadas de ventas |
| AI-15 | Motor de selección de carrier | Recomienda carrier por destino, peso y urgencia | **Planificado** | Carlos Vega (Última milla) | Andrés Kim | A definir | A definir (8 carriers) | Tarifas negociadas y direcciones |
| AI-16 | Motor de aprobación de devoluciones | Aprueba/rechaza devoluciones por reglas configurables | **Planificado** | Sofía Ramos (Logística inversa) | Andrés Kim | A definir | A definir | Devoluciones y datos de cliente |
| AI-17 | Inspección asistida por imagen | Clasifica el estado de un producto devuelto desde una foto | **Planificado** | Sofía Ramos | Andrés Kim | Modelo visión (a definir) | A definir | Imágenes de producto (posible PII) |
| AI-18 | Agente de documentación técnica | Genera y mantiene documentación interna | **Planificado** | Andrés Kim | Andrés Kim | A definir | A definir | Documentación interna |
| AI-19 | Asistente ejecutivo en lenguaje natural | Consultas del CEO sobre KPIs por país | **Planificado** | Thomas Harry (CEO) | Andrés Kim | A definir | A definir | KPIs agregados |
| AI-20 | Agente comercial de propuestas a prospectos | Sugiere servicio y estructura de precios | **Planificado** | Miguel Torres | Andrés Kim | A definir | A definir | Datos de prospectos |

> Nota: el briefing cita "motor de selección de carrier", "motor de aprobación
> de devoluciones" y "dashboard en tiempo real". En este fork el dashboard y los
> datos existen, pero los dos motores **no están implementados**; por eso no
> pueden ser auditados como componentes activos (ver `nist-ai-rmf-report.md` §5,
> brecha NIST-08).

---

## 2. Responsable del control cuando el modelo o la tool es de un tercero

TrackFlow distingue **operación del servicio** (proveedor) de **control del
riesgo** (TrackFlow). El responsable del control es siempre un rol interno
nombrado, aunque la ejecución sea de un tercero.

| Proveedor | Qué aporta | Quién opera | Quién controla en TrackFlow | Evidencia del control |
|---|---|---|---|---|
| **4Geeks LiteLLM proxy** | Puerta de entrada a los modelos (API OpenAI-compatible) | 4Geeks Academy | **Andrés Kim** (CTO) | `LLM_BASE_URL` + `LLM_API_KEY` por env; timeout y fallback por tool; sin claves en código |
| **OpenRouter** | Enrutado a modelos de terceros | OpenRouter | **Andrés Kim** | Selección de modelo por env (`GENERATION_MODEL`, `EMBEDDING_MODEL`); cambio de modelo sin tocar código |
| **Perplexity (embeddings)** | Vectores de 1024 dimensiones | Perplexity | **Andrés Kim** | Dimensión validada en `rag_config.py`; colección versionada |
| **DeepSeek (generación)** | Modelo de chat | DeepSeek | **Andrés Kim** | Temperatura baja, `max_tokens` acotado, output guard y reglas de dominio |
| **Qdrant** | Almacén vectorial | TrackFlow (self-hosted) | **Andrés Kim** | Contenedor propio, puerto no publicado, volumen persistente |
| **Supabase (PostgreSQL)** | Datos de inventario, incidencias y RFP | Supabase (gestionado) | **Andrés Kim** | `DATABASE_URL` por env, pooler, backups y región a cargo de Andrés |
| **Auth0** | Identidad OAuth 2.1 del MCP | Auth0 | **Andrés Kim** | Tenant, `audience`, scopes `mcp:read`/`mcp:write` y rotación del client secret |
| **Resend** | Envío de emails de recuperación | Resend | **Andrés Kim** | `RESEND_API_KEY` por env; sin clave → stub local |
| **MarkItDown (OSS)** | Conversión PDF → Markdown | Comunidad | **Andrés Kim** | Versión fijada en `requirements.txt`; validación `%PDF-`, tamaño y nombre seguro |
| **Redis / Celery** | Cola de tareas | TrackFlow (self-hosted) | **Andrés Kim** | Sin publicar en `0.0.0.0`, reintentos, DLQ y timeouts |

Regla de gobierno: **si el proveedor cambia el modelo o retira una versión, el
control sigue siendo de Andrés Kim**; el proveedor no puede alterar prompt,
guardrails, scopes ni la decisión de publicar una propuesta. Los cambios de
modelo se registran como cambio de configuración (env) y se revalidan con
`tests/pipelines/test_agent_evals.py`.

---

## 3. Matriz RACI resumida

| Actividad | Responsable (R) | Aprobador (A) | Consultado (C) | Informado (I) |
|---|---|---|---|---|
| Inventario y registro de sistemas de IA | Andrés Kim | Thomas Harry | Responsables de área | Comité de dirección |
| Prompt de sistema y guardrails del agente CX | Andrés Kim | Valentina Cruz | Legal/DPO externo | Thomas Harry |
| Publicación de documentos en la KB | Responsable del área dueña del documento | Andrés Kim | Valentina Cruz | Miguel Torres |
| Alta de un modelo o proveedor nuevo | Andrés Kim | Thomas Harry | Seguridad/DPO | Responsables de área |
| Aprobación de una propuesta RFP | Miguel Torres / Sofía Ramos / Ana Whitfield | Thomas Harry (contratos > umbral) | Andrés Kim | Cliente B2B |
| Respuesta a incidente de seguridad de IA | Andrés Kim | Thomas Harry | DPO / asesoría legal | AEPD (si aplica), clientes afectados |
| Rotación de credenciales y scopes | Andrés Kim | Thomas Harry | — | Equipo técnico |

---

## 4. Clasificación de datos y normas aplicables

| Dato | Ejemplos | Sensibilidad | Norma principal |
|---|---|---|---|
| Contacto y dirección B2C | Nombre, dirección, teléfono, email del destinatario | **Alta (PII)** | RGPD (UE) y CCPA/CPRA (California) |
| Datos contractuales B2B | Volumen, incidencias, tarifas negociadas | **Alta (confidencialidad contractual)** | Contratos con la marca + RGPD/CCPA si incluye personas |
| Credenciales e integraciones | API keys de LLM/Qdrant/Resend, JWT, OAuth | **Crítica** | Política interna + RGPD art. 32 |
| Documentos internos | Tarifas publicadas, SLAs, políticas | Media | Confidencialidad interna |
| Telemetría de producto | Eventos de UI sin PII | Baja | Política de privacidad |
| Datos agregados | KPIs, forecast | Baja/Media | Interno |

Principio aplicado: el agente CX **nunca** recibe datos B2B de una marca que no
corresponda a la sesión; las tools de inventario y memoria filtran por rol
(`user` vs `manager`/`admin`) y el RAG separa documentos públicos de internos
(`RAG_PUBLIC_DOCUMENTS` / `RAG_INTERNAL_DOCUMENTS`).

---

## 5. Mantenimiento del inventario

- Se revisa en cada entrega que añada un componente que llame a un modelo,
  reciba documentos externos o exponga tools.
- Cualquier componente nuevo debe entrar con **responsable de negocio**,
  **responsable técnico** y **proveedor** antes de pasar a producción.
- El registro de brechas vive en `nist-ai-rmf-report.md` §5; el registro OWASP
  previo sigue en [`../findings-register.md`](../findings-register.md).
