# TrackFlow — Propuesta de Arquitectura Backend

## 1. Análisis de necesidades

TrackFlow es una empresa de logística que opera en dos países (EE. UU. y España) con siete áreas de negocio bien definidas. Cada área tiene necesidades específicas que el backend debe cubrir:

| Área | Necesidad técnica |
|---|---|
| **Operaciones de Almacén** | API de inventario unificada, pipeline de ingesta de pedidos, alertas de stock bajo |
| **Última Milla** | Motor de selección de transportista, endpoint de tracking agregado, portal de seguimiento |
| **Logística Inversa** | Motor de aprobación automática, flujo de recogida, inspección asistida por IA |
| **Experiencia del Cliente** | Agente CX automático, base de conocimiento semántica (RAG), sistema de tickets |
| **Comercial** | Integración CRM, informes PDF automáticos, salud de cliente con riesgo de renovación |
| **Tecnología** | Telemetría centralizada, logging, monitorización en tiempo real |
| **Dirección Ejecutiva** | Dashboard de KPIs en tiempo real, informe semanal automático |

Los datos fluyen entre todos los dominios (un pedido atraviesa inventario → transportista → tracking → CX), pero cada dominio tiene su propia lógica de negocio y sus propias reglas. Esto hace que una **arquitectura modular con separación por dominio** sea la opción más adecuada.

Se elige **FastAPI** por las siguientes razones:

- Tipado estricto con Pydantic (validación automática de entrada/salida).
- Async nativo para integraciones con APIs externas (8 transportistas, servicios de IA, scraping).
- Documentación OpenAPI generada automáticamente.
- Sistema de dependencias (`Depends`) que facilita la inyección de dependencias y testing.

---

## 2. Monolito modular con Domain-Driven Design

Optamos por un **monolito modular**: una sola aplicación FastAPI que se despliega como un único servicio, pero con el código organizado en módulos que reflejan los límites de cada dominio de negocio.

### Criterio de separación

Cada dominio de negocio se convierte en un módulo autocontenido dentro de `app/domains/`. Un módulo contiene:

- **models.py** — Modelos SQLAlchemy (persistencia en base de datos).
- **schemas.py** — Esquemas Pydantic (serialización request/response).
- **service.py** — Lógica de negocio del dominio.
- **repository.py** — Acceso a datos (consultas a base de datos).
- **exceptions.py** — Excepciones específicas del dominio.

### Reglas de comunicación entre módulos

- Un módulo nunca accede directamente al **repository** de otro módulo.
- Si necesita datos de otro dominio, debe hacerlo a través de su **service**.
- Los **schemas** (Pydantic) son la interfaz compartida entre dominios.

Esto mantiene los módulos desacoplados, testeables de forma independiente, y preparados para ser extraídos a microservicios si el día de mañana el volumen lo requiere.

---

## 3. Estructura de carpetas

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app factory
│   │
│   ├── core/                            # Configuración transversal
│   │   ├── __init__.py
│   │   ├── config.py                    # pydantic-settings (DB_URL, SECRET_KEY, ALLOWED_ORIGINS…)
│   │   ├── database.py                  # SQLAlchemy async engine + session factory
│   │   ├── security.py                  # JWT, auth dependencies
│   │   ├── logging.py                   # Structured logging configuration
│   │   └── dependencies.py              # Dependencias globales (get_db, get_current_user…)
│   │
│   ├── api/                             # Capa de presentación (routers)
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                # Agrega todos los routers de v1
│   │   │   ├── inventory.py             # Endpoints de inventario y almacén
│   │   │   ├── carriers.py              # Endpoints de transportistas
│   │   │   ├── returns.py               # Endpoints de devoluciones
│   │   │   ├── cx.py                    # Endpoints de atención al cliente
│   │   │   ├── sales.py                 # Endpoints de CRM / comercial
│   │   │   ├── executive.py             # Endpoints de dashboard ejecutivo
│   │   │   └── monitoring.py            # Endpoints de health check, telemetría
│   │   └── deps.py                      # Dependencias específicas por ruta
│   │
│   ├── domains/                         # Módulos de dominio de negocio
│   │   ├── inventory/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                # Warehouse, SKU, Stock, Order
│   │   │   ├── schemas.py               # InventoryRequest, InventoryResponse…
│   │   │   ├── service.py               # Lógica de inventario, stock bajo, etc.
│   │   │   ├── repository.py            # Queries a tablas de inventario
│   │   │   └── exceptions.py            # StockNotFound, InsufficientStock…
│   │   │
│   │   ├── carriers/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                # Carrier, Shipment, TrackingEvent
│   │   │   ├── schemas.py               # CarrierSelectRequest, TrackingResponse…
│   │   │   ├── service.py               # Motor de selección, tracking agregado
│   │   │   ├── repository.py
│   │   │   ├── exceptions.py
│   │   │   └── integrations/            # Clientes específicos por carrier
│   │   │       ├── __init__.py
│   │   │       ├── ups.py
│   │   │       ├── fedex.py
│   │   │       ├── dhl.py
│   │   │       ├── mrw.py
│   │   │       └── seur.py
│   │   │
│   │   ├── returns/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                # ReturnRequest, ReturnApproval, Inspection
│   │   │   ├── schemas.py
│   │   │   ├── service.py               # Motor de aprobación, flujo de recogida
│   │   │   ├── repository.py
│   │   │   ├── exceptions.py
│   │   │   ├── inspection.py            # IA clasificación de estado por imagen
│   │   │   └── rules_engine.py          # Reglas configurables por cliente
│   │   │
│   │   ├── cx/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                # Ticket, KnowledgeBaseArticle
│   │   │   ├── schemas.py
│   │   │   ├── service.py               # Agente CX, RAG, análisis de sentimiento
│   │   │   ├── repository.py
│   │   │   └── exceptions.py
│   │   │
│   │   ├── sales/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                # Client, Contract, AccountHealth
│   │   │   ├── schemas.py
│   │   │   ├── service.py               # Riesgo de renovación, informes PDF
│   │   │   ├── repository.py
│   │   │   └── exceptions.py
│   │   │
│   │   └── executive/
│   │       ├── __init__.py
│   │       ├── models.py                # KPI, WeeklyReport, AlertThreshold
│   │       ├── schemas.py
│   │       ├── service.py               # KPIs consolidados, informes semanales
│   │       ├── repository.py
│   │       └── exceptions.py
│   │
│   ├── shared/                          # Utilidades transversales (sin lógica de negocio)
│   │   ├── __init__.py
│   │   ├── base.py                      # Base model SQLAlchemy, CRUD mixin
│   │   ├── pagination.py                # Paginación genérica
│   │   └── types.py                     # Enums compartidos (Country, Currency, OrderStatus…)
│   │
│   └── integrations/                    # Clientes para sistemas externos
│       ├── __init__.py
│       ├── sga_la_client.py             # Integración con SGA de Los Ángeles
│       ├── sga_zgz_client.py            # Integración con SGA de Zaragoza
│       ├── erp_client.py                # Integración con ERP corporativo
│       └── pdf_generator.py             # Generación de informes PDF
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                      # Fixtures globales (test DB, test client…)
│   ├── test_inventory/
│   │   ├── __init__.py
│   │   ├── test_models.py
│   │   ├── test_service.py
│   │   └── test_api.py
│   ├── test_carriers/
│   ├── test_returns/
│   ├── test_cx/
│   ├── test_sales/
│   └── test_executive/
│
├── alembic/                             # Migraciones de base de datos
│   ├── env.py
│   └── versions/
│
├── .env.example                         # Plantilla de variables de entorno
├── requirements.txt
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

---

## 4. Convenciones FastAPI

### Routers

- Los routers viven en `app/api/v1/`, un archivo por dominio.
- Cada router define un prefijo y tags para la documentación:

```python
router = APIRouter(prefix="/v1/inventory", tags=["inventory"])
```

- Todos los routers se agregan en `app/api/v1/router.py` y ese se incluye en `main.py`.

### Schemas (Pydantic)

- Separación estricta entre **request** y **response**:

```python
class ItemCreate(BaseModel):
    sku: str
    quantity: int
    warehouse_id: str

class ItemResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    warehouse_id: str
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)
```

### Configuración centralizada

- Una sola clase `Settings` con `pydantic-settings` que lee de variables de entorno y `.env`.
- Disponible como dependencia global:

```python
from core.config import Settings

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Dependency Injection

- Uso intensivo de `Depends()` para:
  - Sesión de base de datos (`get_db`).
  - Usuario autenticado (`get_current_user`).
  - Configuración (`get_settings`).
  - Permisos por rol.

### Mapeo de errores

- Cada dominio define sus excepciones. Un `exception_handler` global las mapea a códigos HTTP:

```python
@app.exception_handler(StockNotFoundError)
async def stock_not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})
```

---

## 5. Endpoints base propuestos

### Inventory (Almacén)

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/v1/inventory/{sku}` | Stock en tiempo real de un SKU (ambos almacenes) |
| GET | `/v1/inventory/{sku}?warehouse=la` | Stock filtrado por almacén |
| POST | `/v1/orders/ingest` | Ingesta de pedido desde email o API |
| GET | `/v1/warehouses` | Lista de almacenes |
| GET | `/v1/warehouses/{id}/stock` | Stock completo de un almacén |
| GET | `/v1/alerts/low-stock` | Alertas de stock bajo |
| POST | `/v1/alerts/low-stock/configure` | Configurar umbrales de alerta |

### Carriers (Transportistas)

| Método | Endpoint | Descripción |
|---|---|---|
| POST | `/v1/shipments/select-carrier` | Recomendar transportista óptimo |
| POST | `/v1/shipments` | Crear un envío |
| GET | `/v1/tracking/{shipment_id}` | Estado agregado del envío |
| GET | `/v1/carriers` | Lista de transportistas |
| GET | `/v1/carriers/{id}/performance` | Dashboard de rendimiento |
| POST | `/v1/tracking/webhook/{carrier}` | Webhook para eventos de tracking |

### Returns (Devoluciones)

| Método | Endpoint | Descripción |
|---|---|---|
| POST | `/v1/returns/approve` | Evaluar y aprobar/rechazar devolución |
| POST | `/v1/returns/{id}/collect` | Programar recogida |
| POST | `/v1/returns/{id}/inspect` | Clasificar estado del producto devuelto |
| GET | `/v1/returns/analytics` | Patrones y estadísticas de devoluciones |

### Customer Experience (Atención al cliente)

| Método | Endpoint | Descripción |
|---|---|---|
| POST | `/v1/tickets` | Crear ticket |
| GET | `/v1/tickets` | Listar tickets |
| GET | `/v1/tickets/{id}` | Detalle de ticket |
| POST | `/v1/tickets/{id}/resolve` | Resolver ticket automáticamente |
| GET | `/v1/knowledge-base/search?q=...` | Búsqueda semántica en base de conocimiento |
| GET | `/v1/dashboard/cx` | Métricas de CX en tiempo real |

### Sales (Comercial / CRM)

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/v1/clients` | Lista de clientes |
| GET | `/v1/clients/{id}` | Perfil unificado de cliente |
| GET | `/v1/clients/{id}/health` | Salud del cliente y riesgo de renovación |
| GET | `/v1/clients/{id}/contract` | Detalle del contrato |
| POST | `/v1/reports/generate` | Generar informe PDF para cliente |

### Executive (Dirección)

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/v1/executive/kpi` | KPIs consolidados en tiempo real |
| GET | `/v1/executive/kpi?country=spain` | KPIs filtrados por país |
| GET | `/v1/executive/reports/weekly` | Informe semanal generado automáticamente |

### Monitoring (Tecnología)

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/v1/health` | Health check |
| GET | `/v1/health/ready` | Readiness probe |
| GET | `/v1/monitoring/logs` | Logs agregados |
| GET | `/v1/monitoring/metrics` | Métricas de rendimiento |

---

## 6. Separación Frontend / Backend en el monorepo

El proyecto es un monorepo que contiene tanto el frontend como el backend. La organización dentro del mismo repositorio sigue estas reglas:

```
/
├── backend/               → Código Python (FastAPI)
├── uis/                   → Código frontend
├── packages/              → Paquetes compartidos
├── shared/                → Documentación y assets
├── docs/                  → Documentación técnica
└── ...
```

### Comunicación

- **Frontend y backend no comparten código.** No se importan archivos Python desde el frontend ni viceversa.
- La comunicación es exclusivamente a través de la **API REST** expuesta por FastAPI.
- El frontend conoce la URL base de la API a través de una variable de entorno (`VITE_API_URL` o `REACT_APP_API_URL`).

### Variables de entorno

El backend utiliza un archivo `.env` (no versionado) con `pydantic-settings`:

```env
# Backend
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/trackflow
SECRET_KEY=...
ALLOWED_ORIGINS=http://localhost:5173,https://app.trackflow.com
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# Carriers API keys
UPS_API_KEY=...
FEDEX_API_KEY=...
DHL_API_KEY=...

# SGA integrations
SGA_LA_ENDPOINT=...
SGA_ZGZ_ENDPOINT=...
```

El frontend usa su propio `.env`:

```env
VITE_API_URL=http://localhost:8000/v1
```

### CORS

La configuración de CORS en FastAPI se lee desde la variable de entorno `ALLOWED_ORIGINS`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Despliegue

- Al ser un monorepo, todo puede construirse y desplegarse desde un **mismo pipeline CI/CD**.
- En desarrollo, el frontend se sirve en `localhost:5173` y el backend en `localhost:8000` con CORS configurado.
- En producción, un proxy reverso (Nginx) o un API gateway pueden servir ambos desde el mismo dominio (`app.trackflow.com/api/...` → backend, `app.trackflow.com` → frontend).
- Si en el futuro frontend y backend se separan en repositorios distintos, la estructura interna de `backend/` no cambia: solo se actualiza la URL base del frontend y los orígenes permitidos en CORS.

---

## 7. Riesgos

### 7.1 Mezcla de responsabilidades en las capas

Si la lógica de negocio se escribe directamente en los endpoints (routers) o en los modelos de SQLAlchemy, los archivos se vuelven ilegibles y difíciles de testear. Cambiar una regla de negocio (ej.: "el umbral de stock bajo pasa de 10 a 20 unidades") obligaría a tocar múltiples archivos sin un lugar claro donde buscar. Para evitarlo, los routers deben limitarse a validar entrada, llamar al service correspondiente y devolver la respuesta; nunca contener lógica de negocio ni consultas a la base de datos.

### 7.2 Acoplamiento entre dominios

Si un módulo accede directamente al repository de otro dominio (ej.: `returns/repository.py` importa y usa `Inventory` desde `inventory/models.py`), los dominios quedan acoplados. Modificar el modelo de inventario podría romper devoluciones, y extraer devoluciones a un servicio independiente requeriría desenredar todas las dependencias directas. La regla de que los dominios se comuniquen solo a través de services mantiene cada módulo independiente y preparado para escalar.

### 7.3 API sin versionado

Si todos los endpoints se exponen bajo `/api/` sin prefijo de versión (`/v1/`), cualquier cambio en los contratos (renombrar un campo, cambiar el formato de una fecha) rompe a todos los clientes simultáneamente: el frontend actual, el portal de tracking público, las integraciones con carriers y cualquier cliente externo. Al usar `/v1/`, `/v2/`, etc., las versiones pueden coexistir mientras los clientes migran.

---

## 8. Conclusión

La arquitectura propuesta — **monolito modular con FastAPI, separación por dominio de negocio y comunicación estricta entre módulos a través de services** — responde directamente a los problemas actuales de TrackFlow:

- **Inventario fragmentado** → Un módulo `inventory` con una API unificada que consulta ambos almacenes.
- **Seguimiento manual de transportistas** → Un módulo `carriers` con motor de selección y tracking agregado.
- **Devoluciones sin criterios** → Un módulo `returns` con motor de reglas configurables.
- **Consultas repetitivas de clientes** → Un módulo `cx` con agente automático y RAG.
- **Informes ejecutivos manuales** → Un módulo `executive` que consolida KPIs en tiempo real.

Al mantener los módulos independientes pero dentro de una misma aplicación, el equipo de 7 personas puede trabajar en distintos dominios sin pisarse, integrar IA y APIs externas sin acoplar el código, y migrar a microservicios en el futuro si el negocio lo requiere, sin tener que reescribir desde cero.
