# Auditoría de Gestión de Errores — TrackFlow

- Fuente: `docs/ERROR_AUDIT_PROMPT.md`
- Alcance: `services/api` (backend Python), `uis/website` (landing/formulario), `uis/backoffice` (dashboard)
- Nota: el prompt referencia `uis/web`, que no existe; se auditó la estructura real del repo.
- Estado: **finalizado**. Todos los hallazgos están resueltos o marcados como "aplicar a futuro". Detalle de cada fix en el historial de commits.

## Resumen

| # | Hallazgo | Categoría | Estado |
|---|---|---|---|
| 1 | Formulario web no envía nada al backend (falso éxito) | C+A | 🔜 A FUTURO |
| 2 | Token de reset volcado en logs | E | ✅ HECHO |
| 3 | Falso éxito al enviar email de reset | C+B | ✅ HECHO |
| 4 | Credencial admin hardcodeada y logueada | E | 🔜 A FUTURO |
| 5 | PII del candidato en consola del navegador | E | 🔜 A FUTURO (depende de #1) |
| 6 | Fetch sin manejo de errores de red | A | ✅ HECHO |
| 7 | Errores crudos del backend a la UI | D | ✅ HECHO |
| 8 | Errores sin acción para el usuario | H | ✅ HECHO |
| 9 | `file.read()` async sin try | A | ✅ HECHO |
| 10 | Excepción raw del CSV al cliente | D | ✅ HECHO |
| 11 | Handler global 500 sin log del stack | C+B | ✅ HECHO |
| 12 | Operaciones TinyDB sin manejo | A | ⚠️ MITIGADO por #11 |
| 13 | `json()` sin try/catch | A | ✅ HECHO |
| 14 | Sesión invalidada en fallo de red transitorio | C | ✅ HECHO |
| 15 | `login/register` sin captura en contexto | A/B | ✅ CUBIERTO en callers |
| 16 | `refresh()` con commit de estado parcial | B/C | ✅ HECHO |
| 17 | "Enlace enviado" ante fallo de red | C | ✅ HECHO |
| 18 | Sin estados de carga/error/reintento en formulario | G+H | 🔜 A FUTURO (depende de #1) |
| 19 | Sin error boundaries | G+D | ✅ HECHO |
| 20 | Sin estado de error al validar sesión | G | ✅ HECHO |
| 21 | Export/Guardado sin crudo y sin reintento | D+H | ✅ HECHO |
| 22 | Sin `sys.exit` en scripts seed | F | ✅ HECHO |
| 23 | Decode con `errors="replace"` sin validar | A | ✅ HECHO |
| 24 | `analyze_file` sin manejo de errores pandas | A | ✅ HECHO |
| 25 | `fromisoformat` sin try | A | ✅ HECHO |
| 26 | `database.py` sin manejo de `OSError` | A | ✅ HECHO |
| 27 | `catch {}` vacíos en parseo de error | B/C | ✅ HECHO |
| 28 | `catch {}` genéricos en suppliers toggle/delete | C | ✅ HECHO |

## Pendientes — aplicar a futuro

### 1. El formulario de la web "envía" sin hacer ninguna petición — falso éxito — 🔜 APLICAR A FUTURO
- **Archivo:** `uis/website/components/application/ApplicationForm.tsx:134-143`
- **Categoría:** (C) Fallo silencioso + (A) try/catch ausente
- **Problema:** `handleSubmit` recolecta los datos, los imprime con `console.log` y directamente `setSuccess(true)`, `setCurrentStep(1)`, `setFormData({})`. No existe ningún `fetch`/Server Action hacia `services/api`. El usuario ve "Aplicación enviada correctamente" (línea 335) aunque **nunca se envió nada**; los datos se pierden.
- **Corrección:** Implementar envío real a la API con `fetch`/Server Action dentro de `try/catch/finally`, verificar `response.ok` y solo mostrar éxito tras confirmación del servidor.

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

### 18. Sin estados de carga/error/reintento en formulario — 🔜 APLICAR A FUTURO
> **Depende de #1** (mismo componente `ApplicationForm.tsx`): los estados de carga/error/reintento se implementarán junto con el envío real del formulario.
- **Archivo:** `uis/website/components/application/ApplicationForm.tsx:321-337`
- **Categoría:** (G) Estados ausentes + (H) Sin acción
- **Problema:** No hay `isSubmitting`, ni estado de error de red/servidor, ni acción posterior al éxito.
- **Corrección:** Añadir `isSubmitting` con spinner, estado de error con "Reintentar"/contacto y navegación en éxito.

## Pendiente adicional

- `uis/talent-pipeline-tracker` está presente en el repo pero no fue contemplado en el prompt. Pendiente de auditoría.
