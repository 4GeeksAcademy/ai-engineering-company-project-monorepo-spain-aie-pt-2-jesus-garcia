# SERIALIZATION_AUDIT.md — TrackFlow API

Auditoría de serialización del backend (`services/api`). Documenta la situación previa, los cambios aplicados para garantizar que **todos** los endpoints exponen un serializer de respuesta explícito, y las decisiones de diseño sobre el payload de salida.

## Criterios de cumplimiento

1. **Toda ruta JSON declara `response_model` explícito** (contrato de salida documentado en OpenAPI).
2. **Ninguna respuesta devuelve un objeto ORM/TinyDB en crudo** — todo pasa por un modelo Pydantic de salida.
3. **Los listados devuelven solo los campos que los consumidores usan** (payload optimizado).
4. **Los endpoints de escritura aceptan únicamente los campos que deben aceptar**.
5. **Relaciones aplanadas** cuando el cliente no necesita el objeto completo.

Regresión garantizada por `services/api/tests/test_response_contract.py`.

## Estado previo (antes de esta tarea)

| Problema | Endpoints afectados |
|---|---|
| Sin `response_model` (dict crudo) | `POST /api/auth/forgot-password`, `POST /api/auth/reset-password`, `POST /api/auth/change-password`, `GET /health` |
| Listado reusaba el modelo de detalle (campos que nadie consume) | `GET /api/suppliers` (`notes`, `service_zone`, `updated_at`), `GET /api/incidents` (`description` completa) |
| Exposición de ID interno de auth | `GET /inventory/orders` → `user_uuid` crudo |
| Riesgo latente de fuga de credenciales | `get_current_user` devolvía el documento TinyDB completo (incluía `hashed_password`, `password_changed_at`) en memoria del request |

## Estado final por endpoint (31 endpoints)

### Autenticación — `app/routes/auth.py`

| Endpoint | response_model | Notas |
|---|---|---|
| `POST /api/auth/login` | `TokenResponse` | `access_token`, `token_type`, `user` (sin hash). Sin cambios. |
| `POST /api/auth/forgot-password` | `MessageResponse` | Nuevo contrato `{ "message": str }`. 202 genérico anti-enumeración. |
| `POST /api/auth/reset-password` | `MessageResponse` | Nuevo contrato. |
| `POST /api/auth/change-password` | `MessageResponse` | Nuevo contrato. |
| `GET /api/auth/me` | `AuthMeResponse` | `email`, `role`, `profile`. Sin cambios. |

### Usuarios — `app/routes/users.py`

| Endpoint | response_model | Notas |
|---|---|---|
| `POST /api/users` (201) | `User` | Sin cambios; `hashed_password` excluido. |
| `GET /api/users` (admin) | `list[User]` | `id, email, is_active, role, created_at`. No hay consumidor frontend; se mantiene mínimo. |
| `GET /api/users/{id}` / `PUT` | `User` | Sin cambios. |
| `DELETE /api/users/{id}` | 204 | Sin body (excepción del test de contrato). |

### Perfiles — `app/routes/profiles.py`

`GET/PUT /api/profiles/me` → `Profile`. Sin cambios.

### Proveedores — `app/routes/suppliers.py`

| Endpoint | response_model | Notas |
|---|---|---|
| `GET /api/suppliers` | `list[SupplierListItem]` | **Optimizado.** Dropped `notes`, `service_zone`, `updated_at` (no los usa la tabla del backoffice). |
| `GET /api/suppliers/{id}` | `Supplier` | Detalle completo para edición. |
| `POST/PUT /api/suppliers` | `Supplier` | Sin cambios; aceptan solo campos de `SupplierCreate/Update`. |
| `DELETE /api/suppliers/{id}` | 204 | Excepción del test de contrato. |

### Análisis de incidentes (CX) — `app/routes/incidents.py`

| Endpoint | response_model | Notas |
|---|---|---|
| `POST /api/incidents/analyze` | `AnalysisResponse` | Sin cambios (resumen agregado, sin PII). |
| `GET /api/incidents/results/export` | `Response` (CSV) | **Excepción intencionada del test de contrato**: respuesta de archivo (bytes), no objeto JSON. Documentada como tal. |

### Gestor de incidencias — `app/routes/incidents_manager.py`

| Endpoint | response_model | Notas |
|---|---|---|
| `GET /api/incidents` | `list[IncidentListItem]` | **Optimizado.** `description` completa → `description_excerpt` (primeros ~120 chars + `…`); la tabla solo muestra 1 línea. |
| `GET /api/incidents/{id}` | `Incident` | Detalle completo. |
| `POST /api/incidents` (201) | `Incident` | Sin cambios. |
| `PATCH /api/incidents/{id}/status` | `Incident` | Sin cambios. |
| `GET /api/incidents/summary` | `IncidentSummary` | Sin cambios (agregados por status/category/origin/branch). |

### Inventario — `app/routes/inventory.py` (prefijo `/inventory`)

| Endpoint | response_model | Notas |
|---|---|---|
| `GET /inventory/products` | `list[SKURead]` | ORM→schema explícito; `current_stock` calculado por service. Sin cambios. |
| `GET /inventory/products/{id}` | `SKURead` | Sin cambios. |
| `POST /inventory/products` | `SKURead` | Sin cambios. |
| `POST /inventory/orders/inbound` | `StockEntryRead` | Sin cambios (mapa explícito ORM→schema). |
| `POST /inventory/orders/outbound` | `StockExitRead` | Sin cambios. |
| `GET /inventory/orders` | `list[InventoryOrderItem]` | **Optimizado.** `user_uuid` → `user_email` (resuelto contra TinyDB users; `""` si la cuenta ya no existe). Se deja de exponer IDs internos de auth en el listado masivo. |

### Salud — `app/main.py`

`GET /health` → `HealthResponse` (`{ "status": "ok" }`). Nuevo contrato.

## Contratos de salida (payloads finales)

```python
# models.py
class MessageResponse(BaseModel):
    message: str

class HealthResponse(BaseModel):
    status: str

class SupplierListItem(BaseModel):
    id: str
    name: str
    country: str
    categories: list[str]
    rate_per_shipment: float
    currency: str
    status: str
    contact_email: str | None = None

class IncidentListItem(BaseModel):
    id: str
    title: str
    description_excerpt: str
    origin: str
    branch: str
    category: str
    status: str
```

```python
# schemas.py
class InventoryOrderItem(BaseModel):
    id: int
    order_type: str
    sku_id: int
    product_name: str
    warehouse: str
    quantity: int
    user_email: str = ""
    created_at: datetime
```

## Decisiones de diseño

1. **File-download como excepción de contrato.** `GET /api/incidents/results/export` devuelve bytes CSV (no un objeto). Se considera correcto como está y se excluye explícitamente del test de regresión (`FILE_RESPONSE_EXCEPTIONS`).
2. **204 sin body como excepción.** Los `DELETE` de users y suppliers no tienen cuerpo; también se excluyen del test.
3. **Master-detail en suppliers.** La lista devuelve `SupplierListItem`; el modal de edición hace `GET /api/suppliers/{id}` (detail) antes de abrir, para no perder `notes`/`service_zone`.
4. **Excerpt de descripción.** La lista de incidencias expone `description_excerpt` (truncado a ~120 chars) en lugar de la descripción completa; el detalle sigue devolviéndola entera.
5. **`user_email` en vez de `user_uuid`.** El feed de órdenes muestra el email del operador (legible) y deja de filtrar el `doc_id` interno de auth. Los DTO de escritura (`StockEntryRead`/`StockExitRead`) conservan `user_uuid` para auditoría por respuesta de alta.
6. **Whitelist de `get_current_user`.** El contexto de usuario inyectado en las rutas ya no lleva `hashed_password`/`password_changed_at`; solo `id, email, is_active, role, created_at`. Elimina el foot-gun de fuga si un endpoint futuro devuelve `current_user` sin `response_model`.

## Checklist de regresión

`services/api/tests/test_response_contract.py`:

- [x] Toda ruta JSON declara `response_model` (excluidas 204 y export CSV).
- [x] Ningún `response_model` expone `hashed_password`, `password` ni `password_changed_at`.
- [x] `get_current_user` devuelve exactamente `{id, email, is_active, role, created_at}`.
- [x] Listado de suppliers devuelve solo los campos del `SupplierListItem`.
- [x] Listado de incidentes devuelve `description_excerpt` (≤ 121 chars) y `description` solo en el detalle.

## Validación

- `pytest` (services/api): **99 passed** (94 previos + 5 nuevos de contrato).
- `npm run typecheck` (raíz): OK.
- `npm run lint` + `npm run build` (uis/backoffice): OK.
- `npm test` (Vitest backoffice): **32 passed**.