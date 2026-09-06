# TESTING — TrackFlow API (`services/api`)

Suites de pruebas automatizadas del backend FastAPI con `pytest`. Este documento explica **cómo ejecutar** las pruebas, **qué cubre cada suite**, el **plan de casos** incluido y por qué son esos casos, y el **resultado de cobertura**.

## 1. Cómo ejecutar

### Ejecución completa

```bash
cd services/api

# Opción A — entorno existente (venv, flujo del monorepo)
source venv/bin/activate
python -m pytest

# Opción B — con uv (pyproject.toml gestiona las deps)
uv run pytest
```

### Con cobertura

```bash
# Requisito: pytest-cov instalado (ya en requirements.txt y [dependency-groups].dev)
python -m pytest --cov=app --cov-report=term-missing

# O con uv
uv run pytest --cov=app --cov-report=term-missing
```

Requisito de la asignatura: **≥ 70 % de cobertura en el módulo de autenticación**. El módulo de auth está en `app/routes/` (`auth.py`, `users.py`, `profiles.py`), `app/services/user_service.py`, `app/core/security.py` y `app/core/dependencies.py`.

### Frontends

- `uis/backoffice`: no hay suite activa. Jest + ts-jest está contemplado por la rúbrica como **opcional/bonus** para helpers TypeScript (API-042, FE-019). No se ha instalado porque aún no hay helpers de auth aislables ni suite que ejecutar.
- `uis/website`: **sin tests** — el funcionamiento está a medias; se retomará cuando se estabilice.

## 2. Qué cubre cada suite

| Archivo | Ámbito | Casos |
|---|---|---|
| `tests/test_register.py` | `POST /api/users` (registro) + CRUD de usuarios | 19 |
| `tests/test_login.py` | `POST /api/auth/login` + flujos de contraseña (forgot/reset/change) | 15 |
| `tests/test_token.py` | Tokens JWT y `GET /api/auth/me` (mismo `get_current_user` del resto de rutas) | 6 |
| `tests/test_profiles.py` | `GET/PUT /api/profiles/me` | 5 |
| `tests/test_incidents.py` | `POST /api/incidents/analyze` + export CSV (analizador de la Experiencia del cliente) | 10 |
| `tests/test_incident_manager.py` | CRUD + máquina de estados de incidencias | 24 |
| `tests/test_inventory.py` | API de inventario: stock por almacén, inbound/outbound, validaciones, auth, `GET /orders` | 15 |

Total: **94** pruebas (45 de auth/usuario + 34 de incidentes + 15 de inventario).

## 3. Plan de casos (endpoint × happy / edge / failure) y por qué

Cada endpoint se prueba en tres niveles (camino feliz, caso límite, modo de fallo). El criterio es **comprobar lógica de negocio**, no serialización HTTP: se afirma qué devuelve la API (estado, token, perfil enlazado, ausencia de credenciales en el response), no internals de FastAPI/OpenAPI.

### `POST /api/users` (register)

| Nivel | Caso | Por qué se incluye |
|---|---|---|
| Happy | Credenciales válidas → `201` con `role: user` y `is_active: true` | El contrato básico: registrar y persistir |
| Happy | Se crea un `Profile` enlazado (`name`, `user_id`) | El registro debe crear perfil vinculado (requisito del usuario) |
| Happy | Campos “privilegiados” no escalan a admin | Evitar registro que eleve privilegios (sin `role` en `UserCreate`) |
| Edge | Email duplicado → `409` **antes** de un segundo insert | Integridad: no debe duplicar usuarios ni perfiles |
| Failure | Email inválido → `422` sin escribir en BD | Validación previa a escritura (lista de usuarios no crece) |
| Failure | Password < 6 → `422` | Mínimos de seguridad del modelo |

### `POST /api/auth/login`

| Nivel | Caso | Por qué se incluye |
|---|---|---|
| Happy | Credenciales correctas → JWT firmado que `decode_token` resuelve al mismo `sub` | El token debe identificar al usuario correcto |
| Happy | Email con mayúsculas también valida | Normalización de email (case-insensitive) |
| Edge | Usuario existe pero `is_active: false` → `403` | “Cuenta deshabilitada” debe bloquear el acceso |
| Failure | Password errónea → `401` sin `access_token` | No emitir token con credenciales incorrectas |
| Failure | Email inexistente → mismo `401` genérico | No filtrar qué emails existen (anti-enumeración) |

### Token / `get_current_user` (`GET /api/auth/me`)

| Nivel | Caso | Por qué se incluye |
|---|---|---|
| Happy | Token válido → `email` + `role` + `profile` | El token autentica y devuelve el perfil |
| Edge | Token con `exp` cercano (~5 min) aún válido | Catches de expiración cercana (comportamientos de reloj) |
| Failure | Token expirado → `401` | El `exp` se respeta |
| Failure | Token malformado → `401` | Firma/algoritmo inválido no autentica |
| Failure | Token de usuario inexistente → `401` | No dejar pasar un `sub` huérfano |
| Failure | Sin header `Authorization` → `401` | Corte de acceso a endpoints protegidos |

### `GET/PUT /api/profiles/me`

| Nivel | Caso | Por qué se incluye |
|---|---|---|
| Happy | GET tras registro → campos del perfil | El perfil se crea y se puede leer |
| Happy | PUT cambia `name` → el `User` (email) intacto | El perfil es un sub-recurso separado del usuario |
| Edge | PUT con `phone` vacío aceptado y no borra el resto | `ProfileUpdate` permite `None`/vacíos; la actualización es parcial |
| Edge | Usuario sin perfil → `404` | El endpoint `GET /profiles/me` no debe fabricar datos |
| Failure | Sin token → `401` | Protección del recurso |

### CRUD de usuarios (`/api/users/{id}`)

| Nivel | Caso | Por qué se incluye |
|---|---|---|
| Happy | Propietario lee/actualiza/borra su propio usuario | Regla de autorización “admin o propietario” |
| Happy | Admin cambia `role` y lista usuarios | Privilegios de admin |
| Edge | No-admin modifica su propio email | Actualización parcial permitida al dueño |
| Edge | Email que ya usa otro usuario → `409` | Unicidad de email |
| Failure | No-admin cambia `role` → `403` | “Only admins can change role” |
| Failure | Usuario ajeno GET/PUT/DELETE → `403` | No autorizado |
| Failure | Usuario inexistente → `404` | Resoluciones claras de recurso |

### Flujos de contraseña (`forgot` / `reset` / `change`)

| Nivel | Caso | Por qué se incluye |
|---|---|---|
| Happy | `change-password` con password actual correcta → login solo con la nueva | La rotación invalida la antigua |
| Edge | Token de reset válido actualiza contraseña y permite login | Camino end-to-end del reset |
| Edge | Token de reset **anterior** a un cambio de password → `400` | Invalidez por `password_changed_at` (seguridad) |
| Edge | `forgot-password` sobre email inactivo → no se emite token | No enviar enlaces a cuentas deshabilitadas |
| Failure | `change-password` con password actual errónea → `400` | Mensaje explícito de error |
| Failure | `reset-password` con token adulterado o de usuario inexistente → `400` | “Invalid or expired token” |
| Failure | `forgot-password` sobre email inexistente → `202` genérico | Anti-enumeración (misma respuesta siempre) |
| Failure | `change-password` sin token → `401` | Protección |

### API de inventario (`/inventory`)

El módulo (MILESTONE_5) corre sobre SQLModel contra `DATABASE_URL` (en tests, sqlite `test_inventory.db`). El stock es **siempre calculado** de las órdenes (inbound − outbound por almacén); las rutas de escritura exigen admin/manager y las de lectura solo sesión válida.

| Nivel | Caso | Por qué se incluye |
|---|---|---|
| Happy | Inbound incrementa / outbound decrementa el stock **del almacén de la orden** | La unidad de stock de TrackFlow es el almacén; `current_stock_by_warehouse` debe reflejarlo |
| Happy | Mismo SKU en ambos almacenes con stock distinto → `compute_stock` distinto por almacén | Aislamiento de stock entre sedes |
| Edge | Inbound en `zaragoza` no altera el stock de `los_angeles` | El filtrado por `warehouse` en los agregados es correcto |
| Failure | Outbound > disponible → `400` **sin insertar fila** (contadas antes/después) | Check-then-write: orden rechazada no deja rastro |
| Failure | `quantity <= 0` → `422` (validador Pydantic `gt=0`) | Mínimos de negocio en el schema |
| Failure | `warehouse` fuera de `WAREHOUSES` → `400` | Validación de dominio en el service |
| Failure | `sku_id` inexistente → `404` | Resolución clara de recurso |
| Failure | Sin token en lecturas → `401`; POST con role `user` → `403`; GET con usuario normal → `200` | Matriz de auth del módulo (escribir manager, leer sesión) |
| Happy | `GET /orders` devuelve solo campos mapeados (`order_type`, `sku_id`, `product_name`, `warehouse`, `quantity`, `user_uuid`, `created_at`) | Mapeo explícito ORM → schema, sin atributos raw del modelo |

## 4. Resultado de cobertura

Objetivo: ≥ 70 % en el módulo de autenticación. Ejecución con `python -m pytest --cov=app --cov-report=term-missing`:

```
Name                                Stmts   Miss  Cover   Missing
---------------------------------------------------------------
app/core/dependencies.py             32      1    97%   49
app/core/security.py                 26      0   100%
app/routes/auth.py                   43      3    93%   43-44, 57
app/routes/profiles.py               11      0   100%
app/routes/users.py                  25      0   100%
app/services/user_service.py        189     11    94%   123-124, 162-163, 229-230, 241-242, 277-279
---------------------------------------------------------------
TOTAL                               808    121    85%
94 passed
```

El módulo de autenticación queda **≥ 93 %** en todos sus archivos; el total del `app` es **85 %**. El módulo de inventario aporta cobertura propia: `app/routes/inventory.py` **98 %** y `app/services/inventory_service.py` **97 %**. (El resto de archivos con coberturas propias: `incidents`/`main`/etc. se reportan en la salida completa; `suppliers.py` queda sin suite propia — bonus fuera del requisito.)

## 5. Hallazgo con ayuda de IA / bug detectado por los tests

Durante la implementación de la suite, los tests del nuevo módulo de auth detectaron un **bug real de aislamiento de tests**: la tabla TinyDB `profiles` nunca se limpiaba entre tests, por lo que un perfil modificado por un test anterior (p. ej. `name="Nuevo Nombre"`) era devuelto por `GET /api/profiles/me` o `/api/auth/me` en tests posteriores. Se detectó al fallar 5 casos (`test_profiles`, `test_register`, `test_token`) con datos “contaminados”.

**Solución aplicada**: `tests/conftest.py` ahora trunca `users`, `profiles` e `incidents` en un fixture autouse (`_clean_db`) y siembra el admin con `doc_id` determinista. Los 79 tests pasan de forma aislada y reproducible.

Además, los tests confirmaron que el header `Authorization` ausente devuelve `401` (no `403`) en los endpoints protegidos, comportamiento que ahora queda fijado por `test_token.py::test_missing_header_returns_401`.

## 6. Notas técnicas

- `tests/conftest.py` fija `SECRET_KEY=test-secret-key` (antes de importar la app) para poder fabricar tokens expirados/cercanos de forma determinista; `load_dotenv()` no la sobrescribe.
- Aislamiento: cada test arranca con BD vacía (+ admin `admin@test.com`/`admin123`).
- `pytest` y `httpx` ya estaban en `requirements.txt`; se añadió `pytest-cov`. `pyproject.toml` define deps, grupo `dev` y la config de pytest (`testpaths=["tests"]`, `addopts="-q"`).
- No se prueban: internals de generación de OpenAPI, mensajes 404/422 genéricos sin significado de negocio, ni librerías de terceros (`bcrypt`, `python-jose`) salvo cuando hace falta fabricar un token.