# Auditoría de Gestión de Errores — TrackFlow

- Fuente: `docs/ERROR_AUDIT_PROMPT.md`
- Alcance auditado: `services/api` (backend Python), `uis/website` (frontend landing/formulario), `uis/backoffice` (frontend dashboard)
- Nota: el prompt referencia `uis/web`, que no existe; se auditó la estructura real del repo.
- Tipo: auditoría de solo lectura. No se realizaron cambios.

## CRÍTICO

### 1. El formulario de la web "envía" sin hacer ninguna petición — falso éxito — 🔜 APLICAR A FUTURO
- **Archivo:** `uis/website/components/application/ApplicationForm.tsx:134-143`
- **Categoría:** (C) Fallo silencioso + (A) try/catch ausente
- **Problema:** `handleSubmit` recolecta los datos, los imprime con `console.log` y directamente `setSuccess(true)`, `setCurrentStep(1)`, `setFormData({})`. No existe ningún `fetch`/Server Action hacia `services/api`. El usuario ve "Aplicación enviada correctamente" (línea 335) aunque **nunca se envió nada**; los datos se pierden.
- **Corrección:** Implementar envío real a la API con `fetch`/Server Action dentro de `try/catch/finally`, verificar `response.ok` y solo mostrar éxito tras confirmación del servidor.

## ALTO

### 2. Token de reset de contraseña volcado en logs — ✅ HECHO
- **Archivo:** `services/api/app/email_service.py:8-16` y `:34`
- **Categoría:** (E) Filtración de datos sensibles
- **Problema:** Se imprime a stdout el enlace de restablecimiento que contiene el token de reset, y se vuelve a incluir junto a `exc` y el email del destinatario en los logs.
- **Corrección aplicada (commit `a09f863`):** se sustituyó `print` por el módulo `logging`; sin API key se hace `logger.warning` con solo el email (sin token/link), y en la rama de error `logger.error(..., exc_info=True)` sin incluir el enlace. El token solo viaja por el canal de email.

### 3. Falso éxito al enviar email de reset — ✅ HECHO
- **Archivo:** `services/api/app/email_service.py:18-36`
- **Categoría:** (C) Fallo silencioso + (B) catch demasiado amplio
- **Problema:** `except Exception as exc` captura todo error de envío y solo hace `print(...)`, sin re-lanzar. Como consecuencia `forgot_password` (`auth.py:58`) responde 202 aunque el email nunca se envió.
- **Corrección aplicada:** `send_password_reset_email` registra el fallo con `logger.error(..., exc_info=True)` y **re-lanza** la excepción. `forgot_password` (`auth.py`) captura el fallo, lo registra en el servidor con `logger.exception(...)` y **devuelve siempre 202**, preservando la anti-enumeración de emails (el cliente no puede saber si la cuenta existe). La función sigue un único `except Exception` para evitar un `NameError` latente al evaluar `resend.exceptions.Error`.

### 4. Credencial admin por defecto hardcodeada y logueada — 🔜 APLICAR A FUTURO
- **Archivo:** `services/api/seed_users.py:20` y `:36`
- **Categoría:** (E) Filtración de datos sensibles
- **Problema:** `admin@trackflow.com` / `admin123` está hardcodeada y además se imprime en consola al seedear.
- **Corrección:** Cargar la credencial de entorno, no imprimir la contraseña y forzar su rotación tras el primer login.

### 5. PII del candidato volcada a consola del navegador — 🔜 APLICAR A FUTURO
> **Depende de #1** (mismo componente `ApplicationForm.tsx`): se abordará junto con la implementación del envío real del formulario.
- **Archivo:** `uis/website/components/application/ApplicationForm.tsx:138`
- **Categoría:** (E) Filtración de datos sensibles
- **Problema:** `console.log("Enviando datos del formulario:", allData)` expone nombre, email, teléfono, ciudad, país, experiencia, propuesta, URLs y rango salarial.
- **Corrección:** Eliminar el log, o restringirlo a `process.env.NODE_ENV !== "production"` logueando solo un id/summary anónimo.

### 6. Fetch sin manejo de errores de red en la capa API — ✅ HECHO
- **Archivo:** `uis/backoffice/lib/api.ts`
- **Categoría:** (A) try/catch ausente
- **Problema:** Los `fetch()` sin `try/catch` lanzan `TypeError("Failed to fetch")` crudo que se propaga sin normalizar hasta la UI.
- **Corrección aplicada:** se añadió un helper central `request<T>()` que envuelve el `fetch` (error de red → `ApiRequestError(-1)`) y el parseo de `json()`/`blob()` (respuesta corrupta → error tipado). Todos los helpers exportados (`analyzeCsv`, `fetchExportCsv`, suppliers/incidents CRUD, summary) se refactorizaron para usarlo.

### 7. Exposición de errores crudos del backend a la UI — ✅ HECHO
- **Archivos:** `uis/backoffice/app/(protected)/incidents/page.tsx` · `app/(protected)/page.tsx` · `app/(protected)/suppliers/page.tsx`
- **Categoría:** (D) Exposición de errores en crudo
- **Problema:** `setError(err.message)` muestra verbatim el `detail` del backend y "Failed to fetch".
- **Corrección aplicada:** se añadió `friendlyError(err)` en `lib/api.ts` que mapea por código de estado (red/-1, 400, 401, 403, 404, 409, 422, resto) a mensajes amigables en español, sin volcar el `detail` crudo. Se sustituyeron los `setError(...)` de incidencias (carga + cambio de estado), del análisis CSV y de proveedores.

### 8. Errores sin acciones para el usuario — ✅ HECHO
- **Archivos:** `uis/backoffice/app/(protected)/incidents/page.tsx` · `app/(protected)/suppliers/page.tsx`
- **Categoría:** (H) Sin acción para el usuario
- **Problema:** Pantallas de error sin botón de reintentar ni navegación alternativa.
- **Corrección aplicada:** se añadió un estado `reloadKey` (en las deps del effect de carga) y un botón **"Reintentar"** en el bloque de error de incidencias y proveedores.

## MEDIO

### 9. `file.read()` async sin try — ✅ HECHO
- **Archivo:** `services/api/app/api/incidents.py:21`
- **Categoría:** (A) try/catch ausente
- **Problema:** Lectura async del archivo subido fuera de `try`; un error I/O responde 500 genérico en lugar de 400 (input del usuario).
- **Corrección aplicada:** `await file.read()` se envuelve en `try/except OSError` y devuelve `HTTPException(400)`.

### 10. Excepción raw al cliente en CSV — ✅ HECHO
- **Archivos:** `services/api/app/api/incidents.py:23-25` · `services/api/app/incidents/service.py:51`
- **Categoría:** (D) Exposición de errores en crudo
- **Problema:** `detail=str(exc)` e `InvalidFormatError` con el detalle interno de pandas viaja hasta la respuesta HTTP.
- **Corrección aplicada:** se eliminó el texto interno incrustado `({exc})` en `service.py` (cabecera CSV y datos). Se conservan los mensajes de dominio útiles al usuario (p. ej. "el archivo está vacío", columnas que faltan) que usa la validación y dependen de los tests; ya no se filtra el detalle crudo de parseo.

### 11. Handler global 500 sin log del stack trace — ✅ HECHO
- **Archivo:** `services/api/app/main.py:37-39`
- **Categoría:** (C) Fallo silencioso + (B) catch amplio
- **Problema:** Captura todas las excepciones y devuelve 500 genérico sin registrar el stack trace, dificultando el debug.
- **Corrección aplicada:** `logger.exception(...)` con método y ruta en el handler.

### 12. Operaciones TinyDB sin manejo (severidad perdida) — ⚠️ MITIGADO POR #11
- **Archivos:** `services/api/app/api/{suppliers,incidents_manager,auth}.py` · `services/api/app/core/dependencies.py:30-36`
- **Categoría:** (A) try/catch ausente
- **Problema:** Consultas/iteraciones de TinyDB sin `try/except`; fallos escalan a 500 vía handler global.
- **Corrección aplicada:** el handler global 500 ahora registra con `logger.exception(...)` el error real y su stack (#11), de modo que los fallos de DB pierden la severidad concreta pero quedan trazables. No se envolvió cada operación de DB (requiere refactor amplio); se mantiene la lectura de alto riesgo protegida (#9).

### 13. `json()` sin try/catch (respuesta corrupta) — ✅ HECHO
- **Archivo:** `uis/backoffice/lib/api.ts`
- **Categoría:** (A) try/catch ausente
- **Problema:** `return response.json()` rechaza con `SyntaxError` si el body no es JSON válido; no se captura.
- **Corrección aplicada:** el helper central `request()` (commit de #6) envuelve el parseo de `json()` en `try/catch` y lanza `ApiRequestError` con status coherente.

### 14. `fetchMeRequest` invalida sesión en fallo de red transitorio — ✅ HECHO
- **Archivo:** `uis/backoffice/contexts/AuthContext.tsx`
- **Categoría:** (C) Fallo silencioso
- **Problema:** `.catch(() => { clearToken(); })` traga el error; un fallo transitorio invalida una sesión válida y redirige al login sin feedback.
- **Corrección aplicada:** solo se limpia el token en `401` (sesión realmente invalidada). En errores de red/5xx se conserva el token y se expone `sessionError` con reintento.

### 15. `AuthContext.login/register` lanzan sin capturar — ✅ CUBIERTO EN CALLERS
- **Archivo:** `uis/backoffice/contexts/AuthContext.tsx` · `components/auth/LoginForm.tsx` · `components/auth/RegisterForm.tsx`
- **Categoría:** (A/B) try/catch ausente / catch amplio
- **Problema:** Dependen del caller; un futuro caller sin captura genera unhandled rejection.
- **Corrección:** ambos callers (`LoginForm` y `RegisterForm`) capturan y normalizan el error (`401`, `409`, `422`, red). No se añadió duplicado de manejo en el contexto (lo haría redundante el manejo existente).

### 16. `refresh()` con commit de estado parcial — ✅ HECHO
- **Archivo:** `uis/backoffice/app/(protected)/incidents/page.tsx`
- **Categoría:** (B/C) Catch amplio / fallo silencioso
- **Problema:** Lanza dos `await` sin try; si el segundo falla, deja estado parcial y el error se propaga.
- **Corrección aplicada:** `refresh()` usa `Promise.all` (ningún commit parcial) dentro de `try/catch` y muestra `friendlyError` en la UI.

### 17. `ForgotPasswordForm` muestra "enlace enviado" ante fallo de red — ✅ HECHO
- **Archivo:** `uis/backoffice/components/auth/ForgotPasswordForm.tsx`
- **Categoría:** (C) Fallo silencioso
- **Problema:** El `catch {}` es anti-enumeración, pero un fallo de red también muestra "te hemos enviado un enlace".
- **Corrección aplicada:** en error de red (`ApiRequestError` con `status -1`) se muestra "No se pudo conectar…" y se permite reintentar; el resto de errores mantienen la anti-enumeración (se muestra el mensaje genérico de envío).

### 18. Sin estados de carga/error/reintento en formulario — 🔜 APLICAR A FUTURO
> **Depende de #1** (mismo componente `ApplicationForm.tsx`): los estados de carga/error/reintento se implementarán junto con el envío real del formulario.
- **Archivo:** `uis/website/components/application/ApplicationForm.tsx:321-337`
- **Categoría:** (G) Estados ausentes + (H) Sin acción
- **Problema:** No hay `isSubmitting`, ni estado de error de red/servidor, ni acción posterior al éxito.
- **Corrección:** Añadir `isSubmitting` con spinner, estado de error con "Reintentar"/contacto y navegación en éxito.

### 19. Sin error boundaries — ✅ HECHO
- **Archivo:** `uis/website/app/` — se añadieron `error.tsx`, `not-found.tsx` y `global-error.tsx`
- **Categoría:** (G) Estados ausentes + (D) Exposición
- **Problema:** Si un Server/Route component lanza, el usuario ve un error crudo sin mensaje amigable.
- **Corrección aplicada:** `error.tsx` (client) con botón "Reintentar" (`unstable_retry`, Next 16) y enlace a inicio, `not-found.tsx` para 404 y `global-error.tsx` con su propio `<html>/<body>`. No se renderiza `error.message` (evita fuga).

### 20. Sin estado de error al validar sesión — ✅ HECHO
- **Archivos:** `uis/backoffice/contexts/AuthContext.tsx` · `uis/backoffice/app/(protected)/layout.tsx`
- **Categoría:** (G) Estados ausentes
- **Problema:** Cuando `fetchMeRequest` falla, el layout renderea `null` y redirige a `/login` sin mensaje/reintento.
- **Corrección aplicada:** `AuthContext` expone `sessionError` y `retryValidation()`; el layout protegido muestra una pantalla de error con "Reintentar" e "Ir a iniciar sesión" en vez de `null`.

### 21. Export/Guardado sin crudo y sin reintento — ✅ HECHO
- **Archivos:** `uis/backoffice/components/ExportLink.tsx` · `components/suppliers/SupplierForm.tsx` · `components/incidents/IncidentForm.tsx`
- **Categoría:** (D) Exposición + (H) Sin acción
- **Problema:** `setError(err.message)` expone detalle del backend; al guardar no hay reintento sin reabrir el modal.
- **Corrección aplicada:** se usa `friendlyError` (mensajes amigables por status). En los formularios de guardado el diálogo de confirmación permanece abierto ante error, permitiendo reintentar la misma operación mostrando el mensaje real.

## BAJO

### 22. Sin `sys.exit` declarativo en scripts seed
- **Archivos:** `services/api/seed.py:176-177` · `seed_incidents.py:69-71` · `seed_users.py:39-40`
- **Categoría:** (F) Sin sys.exit
- **Problema:** No controlan errores de forma explícita ni usar `sys.exit(1)`; fallos suaves terminan con 0.
- **Corrección:** Envolver en `try/except` y usar `sys.exit(1)` en fallos y `sys.exit(0)` en éxito.

### 23. Decode con `errors="replace"` sin validar
- **Archivo:** `services/api/app/incidents/service.py:41`
- **Categoría:** (A) try/catch ausente
- **Problema:** Evita crash pero silencia datos corruptos sin validar el resultado.
- **Corrección:** Detectar caracteres de reemplazo y emitir error de formato explícito.

### 24. `analyze_file` sin manejo de errores pandas interno
- **Archivo:** `services/api/app/incidents/analyzer.py:91-98`
- **Categoría:** (A) try/catch ausente
- **Problema:** No maneja `ParserError`/`EmptyDataError`; depende del llamador, en CLI podría crashear.
- **Corrección:** Manejar excepciones de pandas o exponer errores de dominio.

### 25. `fromisoformat` sin try
- **Archivo:** `services/api/app/api/auth.py:92`
- **Categoría:** (A) try/catch ausente
- **Problema:** Un valor corrupto en `password_changed_at` lanza `ValueError` → 500.
- **Corrección:** Envolver en `try/except ValueError`.

### 26. `database.py` sin manejo de `OSError`
- **Archivo:** `services/api/database.py:8-10`
- **Categoría:** (A) try/catch ausente
- **Problema:** Fallos de permisos/espacio en `os.makedirs`/`TinyDB` propagan al endpoint.
- **Corrección:** Capturar `OSError` y loguear error de dominio claro.

### 27. `catch {}` vacíos en parseo de error defensivo
- **Archivo:** `uis/backoffice/lib/api.ts:81,98,127,147,169,192,210,236,253,275,298,315`
- **Categoría:** (B/C) Catch amplio / fallo silencioso
- **Problema:** `catch {}` vacíos degradan el motivo a `statusText` poco útil.
- **Corrección:** Al menos `console.error` del error original con fines de log.

### 28. `catch {}` genéricos en suppliers toggle/delete
- **Archivo:** `uis/backoffice/app/(protected)/suppliers/page.tsx:106-108,120-121`
- **Categoría:** (C) Fallo silencioso
- **Problema:** Descartan el objeto de error y muestran mensaje genérico sin traza.
- **Corrección:** Diferenciar `ApiRequestError` (mostrar `err.message`) de errores de red.

## Recomendaciones prioritarias

1. **Formulario web inoperativo (CRÍTICO)** — conectar el envío al backend. 🔜 **Aplicar a futuro** (requiere cambios grandes; arrastra #5 y #18).
2. **Normalizar errores API en backoffice (A+D)** — `ApiRequestError` con mensajes amigables por status.
3. **Frenar fugas de tokens/PII en logs (api + web)** — ✅ parcial (hallazgos #2 y #3 resueltos; fugas en `seed_users.py` (#4) y `ApplicationForm.tsx` (#5) 🔜 a futuro).
4. **Reintentos en páginas de incidencias/proveedores**.
5. **No invalidar sesión por fallo de red transitorio**.

## Pendiente adicional

- `uis/talent-pipeline-tracker` está presente en el repo pero no fue contemplado en el prompt. Pendiente de auditoría.
