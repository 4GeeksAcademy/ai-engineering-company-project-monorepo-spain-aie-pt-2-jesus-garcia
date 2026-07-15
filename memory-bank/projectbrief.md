# Project Brief — TrackFlow

## Descripción
TrackFlow es una empresa de logística de última milla y gestión de almacenes fundada en 2009 en Los Ángeles. Opera en Estados Unidos y España con almacenes en Los Ángeles y Zaragoza (~130 empleados, ~9M€ anuales).

La unidad **TrackFlow Tech** construye los sistemas, integraciones y automatizaciones que necesita la empresa.

## Departamentos y necesidades clave

| Departamento | Responsable | Necesidad principal |
|---|---|---|
| Operaciones de Almacén | Ana Whitfield | API de inventario unificada, pipeline de ingesta de pedidos, dashboard de operaciones, alertas de stock bajo |
| Última Milla y Transportistas | Carlos Vega | Motor de selección de transportista, endpoint unificado de tracking, portal de seguimiento público, dashboard de rendimiento |
| Logística Inversa | Sofía Ramos | Motor de aprobación automática de devoluciones, flujo automatizado de recogida, inspección asistida por IA, dashboard de devoluciones |
| Experiencia del Cliente (CX) | Valentina Cruz | Agente CX automático, base de conocimiento semántica (RAG), sistema unificado de tickets, dashboard en tiempo real, análisis de sentimiento |
| Comercial | Miguel Torres | Integración CRM, informes PDF automáticos, dashboard de salud de cliente, alertas de renovación, agente comercial |
| Tecnología | Andrés Kim | Telemetría y logging centralizados, pipeline de datos, monitorización en tiempo real, agente de documentación técnica, automatización de operaciones |
| Dirección Ejecutiva | Thomas Harry | Dashboard ejecutivo global, informe semanal automático, comparativas por país, alertas por umbrales, asistente IA en lenguaje natural |

## Hitos del proyecto

- **MILESTONE_1** — Landing page y formulario de aplicación (HTML/CSS/JS vanilla)
- **MILESTONE_2** — Modelado de datos, colecciones y validaciones (TypeScript)
- **MILESTONE_3** — Talent Tracker · Recruitment Pipeline (Next.js 16 + React 19 + Tailwind v4)

## Estructura del monorepo

```
/
├── agents/          # Lógica de agentes
├── data/            # Datos: eval, pipelines, process, raw
├── docs/            # Documentación
├── infra/           # Infraestructura
├── internal/        # Documentación interna
├── mcps/            # MCP servers
├── packages/shared/ # Paquetes compartidos
├── scripts/         # Scripts auxiliares
├── services/        # Servicios
├── shared/          # Código compartido
├── src/             # TypeScript (types, utils)
├── uis/             # Frontends (talent-pipeline-tracker)
├── workflows/       # CI/CD pipelines
├── index.html       # Landing page (Hito 1)
├── application.html # Formulario de aplicación (Hito 1)
├── validation.js    # Validación (Hito 1)
└── test/            # Tests
```
