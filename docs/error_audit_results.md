# Auditoría de Gestión de Errores — TrackFlow

- Fuente: `docs/ERROR_AUDIT_PROMPT.md`
- Alcance auditado: `services/api` (backend Python), `uis/website` (frontend landing/formulario), `uis/backoffice` (frontend dashboard)
- Nota: el prompt referencia `uis/web`, que no existe; se auditó la estructura real del repo.
- Tipo: auditoría de solo lectura. No se realizaron cambios.

## CRÍTICO

### 1. El formulario de la web "envía" sin hacer ninguna petición — falso éxito
- **Archivo:** `uis/website/components/application/ApplicationForm.tsx:134-143`
- **Categoría:** (C) Fallo silencioso + (A) try/catch ausente
- **Problema:** `handleSubmit` recolecta los datos, los imprime con `console.log` y directamente `setSuccess(true)`, `setCurrentStep(1)`, `setFormData({})`. No existe ningún `fetch`/Server Action hacia `services/api`. El usuario ve "Aplicación enviada correctamente" (línea 335) aunque **nunca se envió nada**; los datos se pierden.
- **Corrección:** Implementar envío real a la API con `fetch`/Server Action dentro de `try/catch/finally`, verificar `response.ok` y solo mostrar éxito tras confirmación del servidor.

## ALTO

### 2. Token de reset de contraseña volcado en logs
- **Archivo:** `services/api/app/email_service.py:8-16` y `:34`
- **Categoría:** (E) Filtración de datos sensibles
- **Problema:** Se imprime a stdout el enlace de restablecimiento que contiene el token de reset, y se vuelve a incluir junto a `exc` y el email del destinatario en los logs.
- **Corrección:** Nunca imprimir el token/link (solo canalizarlo por email); usar el módulo `logging` y mensajes genéricos sin token ni datos personales.

### 3. Falso éxito al enviar email de reset
- **Archivo:** `services/api/app/email_service.py:18-36`
- **Categoría:** (C) Fallo silencioso + (B) catch demasiado amplio
- **Problema:** `except Exception as exc` captura todo error de envío y solo hace `print(...)`, sin re-lanzar. Como consecuencia `forgot_password` (`auth.py:58`) responde 202 aunque el email nunca se envió.
- **Corrección:** Capturar excepciones específicas del SDK de `resend`, usar `logging.error(..., exc_info=True)` y no devolver 202 en falso ante fallo real.

### 4. Credencial admin por defecto hardcodeada y logueada
- **Archivo:** `services/api/seed_users.py:20` y `:36`
- **Categoría:** (E) Filtración de datos sensibles
- **Problema:** `admin@trackflow.com` / `admin123` está hardcodeada y además se imprime en consola al seedear.
- **Corrección:** Cargar la credencial de entorno, no imprimir la contraseña y forzar su rotación tras el primer login.

### 5. PII del candidato volcada a consola del navegador
- **Archivo:** `uis/website/components/application/ApplicationForm.tsx:138`
- **Categoría:** (E) Filtración de datos sensibles
- **Problema:** `console.log("Enviando datos del formulario:", allData)` expone nombre, email, teléfono, ciudad, país, experiencia, propuesta, URLs y rango salarial.
- **Corrección:** Eliminar el log, o restringirlo a `process.env.NODE_ENV !== "production"` logueando solo un id/summary anónimo.

### 6. Fetch sin manejo de errores de red en la capa API
- **Archivo:** `uis/backoffice/lib/api.ts:42,70,89,120,138,158,181,200,229,244,264,287,306`
- **Categoría:** (A) try/catch ausente
- **Problema:** Los `fetch()` sin `try/catch` lanzan `TypeError("Failed to fetch")` crudo que se propaga sin normalizar hasta la UI.
- **Corrección:** Envolver cada `fetch` en `try/catch` y lanzar `ApiRequestError` tipado con mensaje amigable.

### 7. Exposición de errores crudos del backend a la UI
- **Archivos:** `uis/backoffice/app/(protected)/incidents/page.tsx:82,111` · `app/(protected)/page.tsx:30-34` · `app/(protected)/suppliers/page.tsx:68`
- **Categoría:** (D) Exposición de errores en crudo
- **Problema:** `setError(err.message)` muestra verbatim el `detail` del backend y "Failed to fetch".
- **Corrección:** Mapear por `status` a mensajes amigables en español y loggear el detalle técnico por separado.

### 8. Errores sin acciones para el usuario
- **Archivos:** `uis/backoffice/app/(protected)/incidents/page.tsx:186-190` · `app/(protected)/suppliers/page.tsx:205-211`
- **Categoría:** (H) Sin acción para el usuario
- **Problema:** Pantallas de error sin botón de reintentar ni navegación alternativa.
- **Corrección:** Añadir botón "Reintentar" que vuelva a llamar a `load()`.

## MEDIO

### 9. `file.read()` async sin try
- **Archivo:** `services/api/app/api/incidents.py:21`
- **Categoría:** (A) try/catch ausente
- **Problema:** Lectura async del archivo subido fuera de `try`; un error I/O responde 500 genérico en lugar de 400 (input del usuario).
- **Corrección:** Envolver `await file.read()` en `try/except (OSError, ...)` y convertir a `HTTPException(400, ...)`.

### 10. Excepción raw al cliente en CSV
- **Archivos:** `services/api/app/api/incidents.py:23-25` · `services/api/app/incidents/service.py:51`
- **Categoría:** (D) Exposición de errores en crudo
- **Problema:** `detail=str(exc)` e `InvalidFormatError` con el detalle interno de pandas viaja hasta la respuesta HTTP.
- **Corrección:** Devolver mensaje genérico mapeado ("CSV inválido") y loguear el detalle técnico aparte.

### 11. Handler global 500 sin log del stack trace
- **Archivo:** `services/api/app/main.py:37-39`
- **Categoría:** (C) Fallo silencioso + (B) catch amplio
- **Problema:** Captura todas las excepciones y devuelve 500 genérico sin registrar el stack trace, dificultando el debug.
- **Corrección:** `logger.exception(..., exc_info=True)` dentro del handler.

### 12. Operaciones TinyDB sin manejo (severidad perdida)
- **Archivos:** `services/api/app/api/{suppliers,incidents_manager,auth}.py` · `services/api/app/core/dependencies.py:30-36`
- **Categoría:** (A) try/catch ausente
- **Problema:** Consultas/iteraciones de TinyDB sin `try/except`; fallos escalan a 500 vía handler global.
- **Corrección:** Acotar el manejo en lecturas de alto riesgo y/o loggear el detalle en el handler global.

### 13. `json()` sin try/catch (respuesta corrupta)
- **Archivo:** `uis/backoffice/lib/api.ts:60,85,102,131,151,173,196,240,257,279,302,319`
- **Categoría:** (A) try/catch ausente
- **Problema:** `return response.json()` rechaza con `SyntaxError` si el body no es JSON válido; no se captura.
- **Corrección:** Capturar el error de parseo y lanzar `ApiRequestError` con status coherente.

### 14. `fetchMeRequest` invalida sesión en fallo de red transitorio
- **Archivo:** `uis/backoffice/contexts/AuthContext.tsx:70-73`
- **Categoría:** (C) Fallo silencioso
- **Problema:** `.catch(() => { clearToken(); })` traga el error; un fallo transitorio invalida una sesión válida y redirige al login sin feedback.
- **Corrección:** No limpiar el token en fallos de red; permitir reintento y registrar el motivo real.

### 15. `AuthContext.login/register` lanzan sin capturar
- **Archivo:** `uis/backoffice/contexts/AuthContext.tsx:83-102`
- **Categoría:** (A/B) try/catch ausente / catch amplio
- **Problema:** Dependen del caller; un futuro caller sin captura genera unhandled rejection.
- **Corrección:** Capturar y normalizar a `ApiRequestError` aquí mismo o garantizar captura en todos los callers.

### 16. `refresh()` con commit de estado parcial
- **Archivo:** `uis/backoffice/app/(protected)/incidents/page.tsx:46-59`
- **Categoría:** (B/C) Catch amplio / fallo silencioso
- **Problema:** Lanza dos `await` sin try; si el segundo falla, deja estado parcial y el error se propaga.
- **Corrección:** Envolver en `try/catch`, exponer el error en la UI y evitar commit parcial (o `Promise.all`).

### 17. `ForgotPasswordForm` muestra "enlace enviado" ante fallo de red
- **Archivo:** `uis/backoffice/components/auth/ForgotPasswordForm.tsx:17-22`
- **Categoría:** (C) Fallo silencioso
- **Problema:** El `catch {}` es anti-enumeración, pero un fallo de red también muestra "te hemos enviado un enlace".
- **Corrección:** Distinguir errores de red ("No se pudo conectar. Reintenta.") sin romper la anti-enumeración.

### 18. Sin estados de carga/error/reintento en formulario
- **Archivo:** `uis/website/components/application/ApplicationForm.tsx:321-337`
- **Categoría:** (G) Estados ausentes + (H) Sin acción
- **Problema:** No hay `isSubmitting`, ni estado de error de red/servidor, ni acción posterior al éxito.
- **Corrección:** Añadir `isSubmitting` con spinner, estado de error con "Reintentar"/contacto y navegación en éxito.

### 19. Sin error boundaries
- **Archivo:** `uis/website/app/` — no existen `error.tsx`, `not-found.tsx`, `global-error.tsx`
- **Categoría:** (G) Estados ausentes + (D) Exposición
- **Problema:** Si un Server/Route component lanza, el usuario ve un error crudo sin mensaje amigable.
- **Corrección:** Añadir `error.tsx`, `not-found.tsx` y `global-error.tsx` sin exponer `error.message`.

### 20. Sin estado de error al validar sesión
- **Archivos:** `uis/backoffice/contexts/AuthContext.tsx:50-81` · `uis/backoffice/app/(protected)/layout.tsx:22-30`
- **Categoría:** (G) Estados ausentes
- **Problema:** Cuando `fetchMeRequest` falla, el layout renderea `null` y redirige a `/login` sin mensaje/reintento.
- **Corrección:** Añadir estado de "error al validar sesión" con reintento.

### 21. Export/Guardado sin crudo y sin reintento
- **Archivos:** `uis/backoffice/components/ExportLink.tsx:26-30,45` · `components/suppliers/SupplierForm.tsx:76` · `components/incidents/IncidentForm.tsx:58`
- **Categoría:** (D) Exposición + (H) Sin acción
- **Problema:** `setError(err.message)` expone detalle del backend; al guardar no hay reintento sin reabrir el modal.
- **Corrección:** Mensajes amigables por `status` y acción de reintento sobre la misma operación.

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

1. **Formulario web inoperativo (CRÍTICO)** — conectar el envío al backend.
2. **Normalizar errores API en backoffice (A+D)** — `ApiRequestError` con mensajes amigables por status.
3. **Frenar fugas de tokens/PII en logs (api + web)**.
4. **Reintentos en páginas de incidencias/proveedores**.
5. **No invalidar sesión por fallo de red transitorio**.

## Pendiente adicional

- `uis/talent-pipeline-tracker` está presente en el repo pero no fue contemplado en el prompt. Pendiente de auditoría.
