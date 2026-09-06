## Hito 5 — Backend: Inventory Management con ORM y doble base de datos

El equipo de Operaciones de Almacén necesita una API de inventario unificada que devuelva el stock en tiempo real de cualquier SKU en cualquiera de los dos almacenes (Los Ángeles y Zaragoza). Hoy los dos SGA no comparten visibilidad del inventario y las discrepancias se detectan tarde. Tu trabajo es construir el módulo de inventario en el backend (`services/api/`) usando un ORM (SQLModel) contra una base de datos PostgreSQL real (Supabase), manteniendo TinyDB como fuente de verdad única para usuarios y autenticación.

### Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    Aplicación FastAPI                        │
├──────────────────────────┬──────────────────────────────────┤
│  TinyDB (existente)      │  Supabase / PostgreSQL (nuevo)   │
│  • users                 │  • skus                          │
│  • auth tokens           │  • stock_entries (inbound)       │
│  • get_current_user()    │  • stock_exits (outbound)        │
└──────────────────────────┴──────────────────────────────────┘
         ▲                              ▲
         │ JWT / session lookup         │ SQLModel session por request
         │                              │ (Depends(get_db))
```

- **TinyDB** sigue siendo la fuente de verdad única para usuarios y autenticación (hitos previos).
- **Supabase** almacena todas las entidades de inventario. No se replica ninguna tabla de usuarios en PostgreSQL.
- Los registros de orden almacenan `user_uuid` como string plano que referencia al usuario TinyDB que creó la orden.

### Entidades del dominio

| Referencia genérica | Nombre TrackFlow | Campos mínimos |
|---|---|---|
| `<ProductEquivalent>` | `SKU` (`sku`) | `id`, `name`, `sku_code`, `warehouse` + campos específicos del contexto |
| `<InboundEquivalent>` | `StockEntry` (`stock_entry`) | `id`, `sku_id`, `quantity`, `warehouse`, `created_at`, `user_uuid` |
| `<OutboundEquivalent>` | `StockExit` (`stock_exit`) | `id`, `sku_id`, `quantity`, `warehouse`, `created_at`, `user_uuid` |

> TrackFlow opera con dos almacenes, así que el stock es **por almacén**: cada SKU pertenece a una `warehouse` y cada entrada/salida registra el almacén en el que ocurre. Los valores admitidos son **`los_angeles`** y **`zaragoza`** (constante `WAREHOUSES` en `inventory_service.py`).

### Estructura de archivos

```
services/api/
├── database.py               # TinyDB client + SQLModel engine + get_db dependency
├── models.py                 # SQLModel table models (ORM únicamente)
├── schemas.py                # Pydantic request/response schemas (separados del ORM)
├── seed_inventory.py         # Seed determinista e idempotente (SKUs + entradas/salidas iniciales)
└── app/
    ├── main.py                     # FastAPI — registra inventory_router, create_all on startup
    ├── routes/
    │   └── inventory.py            # APIRouter(prefix="/inventory") — solo delegación a inventory_service
    └── services/
        └── inventory_service.py    # Lógica de negocio: compute_stock, validación outbound
```

`tests/test_inventory.py` es entregable obligatorio: cubre el cálculo de stock por almacén y el rechazo de outbound sin stock disponible.

### Configuración de base de datos

#### Conexión a Supabase

En el dashboard de Supabase (**Connect → Direct**), elige **Transaction pooler** como método de conexión y **URI** como tipo — copia esa cadena en `DATABASE_URL`. No uses la cadena de conexión directa (puerto `5432`); la URI del pooler usa el puerto `6543` y un host `*.pooler.supabase.com`.

Ver las capturas en la carpeta `.learn/` de la raíz del proyecto (`supabase-transaction-pooler-uri.png`, `supabase-transaction-pooler-connection-string.png`).

#### Variables de entorno (`.env`)

```env
# Existentes — no eliminar
TINYDB_PATH=...
JWT_SECRET=...
ACCESS_TOKEN_EXPIRE_MINUTES=...

# Nuevas para este hito — Transaction pooler URI de Supabase
DATABASE_URL=postgresql://postgres.[project-ref]:password@aws-0-region.pooler.supabase.com:6543/postgres
```

Nunca hardcodear credenciales. Confirmar que `.env` está listado en `.gitignore`.

#### Patrón de `database.py`

```python
from sqlmodel import Session, SQLModel, create_engine
from tinydb import TinyDB


tinydb = TinyDB(os.getenv("TINYDB_PATH"))
engine = create_engine(os.getenv("DATABASE_URL"), echo=False)


def get_db():
    with Session(engine) as session:
        yield session
```

- `database.py` inicializa **ambas** conexiones (TinyDB y SQLModel engine) en un único módulo importable.
- `get_db` cede una sesión por request vía `Depends()` — sin variable global `Session`.

#### Inicialización del esquema

Al arrancar la aplicación, en el lifespan de `app/main.py`:

```python
SQLModel.metadata.create_all(engine)
```

### Modelos ORM (`models.py`)

Reglas:

- Usar `SQLModel, table=True` — no modelos declarativos SQLAlchemy en bruto.
- Declarar FK con `Field(foreign_key="sku.id")` (nombre real de la tabla de productos).
- `user_uuid` es `str`, sin FK a una tabla de usuarios en Supabase.
- **No** añadir una columna `current_stock` almacenada en la tabla de productos.

```python
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel


class SKU(SQLModel, table=True):
    __tablename__ = "sku"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    sku_code: str = Field(index=True)
    warehouse: str


class StockEntry(SQLModel, table=True):
    __tablename__ = "stock_entry"
    id: int | None = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="sku.id")
    quantity: int
    warehouse: str
    user_uuid: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    product: SKU = Relationship()


class StockExit(SQLModel, table=True):
    __tablename__ = "stock_exit"
    id: int | None = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="sku.id")
    quantity: int
    warehouse: str
    user_uuid: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    product: SKU = Relationship()
```

Las cantidades de inventario de TrackFlow se cuentan en unidades enteras (piezas): `quantity` es `int`, no `float`. La relación `product` permite el eager-load de `GET /inventory/orders`.

### Schemas Pydantic (`schemas.py`)

Separar schemas de request y response de los modelos ORM — usar nombres del contexto:

- `SKUCreate`, `SKURead` (con `current_stock` calculado: `current_stock`, `current_stock_by_warehouse`)
- `StockEntryCreate`, `StockEntryRead`
- `StockExitCreate`, `StockExitRead`
- Item combinado para `GET /inventory/orders` (orden + resumen del producto anidado + `user_uuid`)

Nunca devolver una instancia SQLModel en bruto desde un endpoint — mapear ORM → schema explícitamente.

### Router de inventario (`app/routes/inventory.py`)

Registrar con `prefix="/inventory"` e incluirlo en `main.py`.

| Método | Path                         | Auth                                  | Descripción                                                    |
| ------ | ---------------------------- | ------------------------------------- | -------------------------------------------------------------- |
| `GET`  | `/inventory/products`        | `get_current_user`                    | Listar productos con `current_stock` y stock por almacén     |
| `POST` | `/inventory/products`        | `require_manager`                     | Crear producto (empieza con stock cero)                        |
| `GET`  | `/inventory/products/{id}`   | `get_current_user`                    | Producto individual con `current_stock`                      |
| `POST` | `/inventory/orders/inbound`  | `require_manager`                     | Registrar orden inbound; incrementa el stock                   |
| `POST` | `/inventory/orders/outbound` | `require_manager`                     | Registrar orden outbound; decrementa el stock                  |
| `GET`  | `/inventory/orders`          | `get_current_user`                    | Listar todas las órdenes con datos del producto y `user_uuid` |

Decisión de diseño: **todas** las rutas requieren autenticación (dato operativo interno; no hay endpoints públicos bajo `/inventory`). Las rutas de escritura exigen role `admin`/`manager` vía `require_manager`; las de lectura solo requieren sesión válida (`get_current_user`). Persistir `current_user.uuid` en `user_uuid` al crear la orden.

### Lógica de negocio — cálculo de stock

`current_stock` es **siempre calculado**, nunca almacenado. La lógica vive en `app/services/inventory_service.py`:

```python
from sqlmodel import Session, func, select

from models import StockEntry, StockExit

WAREHOUSES = ("los_angeles", "zaragoza")


def compute_stock(session: Session, sku_id: int, warehouse: str) -> int:
    inbound = session.exec(
        select(func.coalesce(func.sum(StockEntry.quantity), 0))
        .where(StockEntry.sku_id == sku_id, StockEntry.warehouse == warehouse)
    ).one()
    outbound = session.exec(
        select(func.coalesce(func.sum(StockExit.quantity), 0))
        .where(StockExit.sku_id == sku_id, StockExit.warehouse == warehouse)
    ).one()
    return inbound - outbound
```

TrackFlow exige stock **por almacén**: `compute_stock` filtra ambos sumatorios por `warehouse` y devuelve el stock de un almacén concreto. Para `SKURead` se recorre `WAREHOUSES` y `current_stock` es la suma de ambos, con desglose en `current_stock_by_warehouse`.

### Validación de outbound

Antes de persistir una orden outbound (check-then-write antes del `session.add`):

1. Calcular el stock disponible del producto **en el almacén indicado por la orden** (`compute_stock(session, sku_id, warehouse)`).
2. Si `requested_quantity > available`, devolver `HTTP 400` con mensaje descriptivo **sin escribir nada** en la BD.
3. Solo si la validación pasa, insertar el registro outbound.

Ejemplo de error:

```json
{
  "detail": "Stock insuficiente para SKU 'CLT-SNK-W-42'. Disponible: 5, solicitado: 10."
}
```

### Evitar N+1

Para `GET /inventory/orders`, usar **`selectinload`** para cargar los productos con eager-load en una sola query — nunca buscar cada producto dentro de un loop.

### Ejemplos de API (indicativos)

#### `GET /inventory/products` (extracto)

```json
[
  {
    "id": 1,
    "name": "Classic White Sneaker - Size 42",
    "sku_code": "CLT-SNK-W-42",
    "warehouse": "los_angeles",
    "current_stock": 47,
    "current_stock_by_warehouse": {"los_angeles": 47, "zaragoza": 0}
  }
]
```

#### `POST /inventory/orders/inbound` (request)

```json
{
  "sku_id": 1,
  "quantity": 20,
  "warehouse": "zaragoza"
}
```

#### `POST /inventory/orders/outbound` — rechazada (400)

```json
{
  "detail": "Stock insuficiente. Disponible: 3, solicitado: 5."
}
```

#### `GET /inventory/orders` (extracto)

```json
[
  {
    "id": 1,
    "order_type": "inbound",
    "sku_id": 1,
    "product_name": "Classic White Sneaker - Size 42",
    "warehouse": "zaragoza",
    "quantity": 20,
    "user_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "created_at": "2025-06-01T10:30:00Z"
  }
]
```

### Checklist de validación (revisores)

- [ ] Dos conexiones a BD activas: TinyDB para auth, Supabase/SQLModel para inventario.
- [ ] Todas las rutas de inventario bajo `/inventory` vía un `APIRouter` dedicado.
- [ ] SQLModel FK: inbound/outbound → entidad producto-equivalente nombrada en CONTEXT.md (`sku`).
- [ ] `current_stock` calculado desde las órdenes — sin endpoint de mutación directa de stock.
- [ ] El cálculo de stock es **por almacén** (`WAREHOUSES`); `current_stock` es la suma de ambos almacenes.
- [ ] Outbound que excede el stock devuelve `400` **antes** de cualquier escritura (check-then-write).
- [ ] Cada orden almacena el `user_uuid` autenticado desde TinyDB.
- [ ] Todas las rutas requieren auth; las de escritura exigen `require_manager` (no hay endpoints públicos).
- [ ] `models.py` y `schemas.py` están separados; los endpoints devuelven solo schemas Pydantic.
- [ ] `get_db` inyectado por request; sin sesión global.
- [ ] Cadenas de conexión en `.env`; `.env` en `.gitignore`.
- [ ] Nombres de entidades y campos coinciden con el CONTEXT.md del estudiante.
- [ ] `seed_inventory.py` es idempotente; `GET /inventory/products` refleja el stock neto de esas semillas.
- [ ] `tests/test_inventory.py` cubre el cálculo de stock por almacén y el rechazo de outbound sin stock.

### Decisiones clave de implementación

- Reutilizar la capa de auth existente — no reconstruir gestión de usuarios en Supabase.
- La lógica de inventario vive en `app/services/inventory_service.py`; `app/routes/inventory.py` solo delega. `compute_stock` es la única función de cálculo de stock.
- La validación de outbound es **check-then-write**: se calcula el stock disponible y, si es insuficiente, se devuelve `400` antes de cualquier `session.add`.
- Validaciones de negocio obligatorias en cada orden: `quantity > 0`, `warehouse` ∈ `WAREHOUSES`, y el `sku_id` debe existir (404 si no). Documentadas en código y tests.

### Criterios de aceptación

1. `services/api/database.py` inicializa TinyDB y la engine SQLModel contra `DATABASE_URL`; `get_db` cede una sesión por request vía `Depends()`.
2. `models.py` define `SKU`, `StockEntry` y `StockExit` con `SQLModel, table=True`, FK `sku_id → sku.id`, `quantity: int`, relación `product` y `user_uuid` como `str` sin FK.
3. No existe ninguna columna `current_stock` almacenada en la tabla de SKUs.
4. `app/routes/inventory.py` registra `APIRouter(prefix="/inventory")` con los endpoints GET/POST de productos y órdenes inbound/outbound; `app/main.py` lo incluye y ejecuta `SQLModel.metadata.create_all(engine)` en el lifespan.
5. `app/services/inventory_service.py` contiene `compute_stock(session, sku_id, warehouse)` y el check-then-write de outbound; `inventory.py` solo delega.
6. `POST /inventory/orders/inbound` incrementa el stock disponible y `POST /inventory/orders/outbound` lo decrementa; ninguna orden altera un contador almacenado.
7. `POST /inventory/orders/outbound` con cantidad mayor al stock del almacén devuelve `400` con mensaje descriptivo y **no** inserta ningún registro.
8. El stock se calcula por almacén (`WAREHOUSES` = `los_angeles` / `zaragoza`); `GET /inventory/products` devuelve `current_stock` y desglose `current_stock_by_warehouse`.
9. Cada orden registra el `user_uuid` del usuario autenticado vía `get_current_user`; las rutas de escritura exigen `require_manager` y ninguna ruta de `/inventory` es pública.
10. `schemas.py` separa request/response del ORM y ningún endpoint devuelve instancias SQLModel en bruto.
11. `GET /inventory/orders` usa `selectinload` (única query, sin N+1) y devuelve el item combinado con `order_type`, datos del producto, `warehouse` y `user_uuid`.
12. `GET /inventory/products` refleja el stock neto de los datos semilla cargados por `seed_inventory.py` (script idempotente).
13. `DATABASE_URL` está en `.env` (`.env.example` con valor vacío), sin credenciales hardcodeadas, y `.env` está en `.gitignore`.
14. `pip install -r requirements.txt` incluye `sqlmodel` y `psycopg2-binary`; `tests/test_inventory.py` cubre el cálculo de stock por almacén y el rechazo de outbound, y todos los tests de `services/api` pasan (`pytest`).