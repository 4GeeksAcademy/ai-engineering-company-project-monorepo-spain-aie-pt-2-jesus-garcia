## Auditoría
### Paths:
```
- services/api (backend - python)
- uis/web (frontend - Nextjs - landing y formulario)
- uis/backoffice (frontend - Nextjs - dashboard)
```

### Prompt
Eres un ingeniero de software senior auditando un repositorio en busca de problemas en la gestión de errores.

Analiza todo el repositorio ubicado en [ruta o describe la estructura de tu repo, por ejemplo: "un frontend Next.js en /apps/web, un backend FastAPI en /apps/api y scripts Python en /scripts"].

Por cada archivo o módulo que revises, identifica y reporta:

1. TRY/CATCH AUSENTE — operaciones asíncronas (fetch, await, lectura de archivos, parseo de JSON) que no tienen ningún manejo de errores.
2. CATCH DEMASIADO AMPLIO — bloques try/catch o try/except que envuelven funciones enteras o secciones grandes de código en lugar de la operación peligrosa concreta.
3. FALLOS SILENCIOSOS — errores capturados pero ignorados (bloques catch vacíos, `except: pass` sin acción).
4. EXPOSICIÓN DE ERRORES EN CRUDO — lugares donde un mensaje de excepción, stack trace o código de estado podría llegar a la interfaz de usuario o a la respuesta de la API.
5. FILTRACIÓN DE DATOS SENSIBLES — salidas de error o logs que podrían incluir secretos, cadenas de conexión a base de datos, rutas internas o datos personales.
6. ESTADOS DE CARGA/ERROR AUSENTES EN LA UI — componentes del frontend que cargan datos pero no renderizan nada (o se rompen) cuando la petición está cargando o falla.
7. SIN LLAMADA A LA ACCIÓN PARA EL USUARIO — estados de error que muestran un mensaje pero no ofrecen ninguna salida (sin reintentar, sin navegación, sin contacto de soporte).
8. SIN sys.exit EN FALLO DE SCRIPT — scripts Python que encuentran un error crítico pero terminan con código 0 o sin código de salida explícito.

Por cada hallazgo, reporta:
- Ruta del archivo y número de línea (o rango)
- Categoría (de la lista anterior)
- Una línea describiendo el problema
- Corrección sugerida (breve — la implementación es responsabilidad del desarrollador)

No hagas ningún cambio. Entrega únicamente el informe de auditoría.
Prioriza los hallazgos por severidad: CRÍTICO > ALTO > MEDIO > BAJO.