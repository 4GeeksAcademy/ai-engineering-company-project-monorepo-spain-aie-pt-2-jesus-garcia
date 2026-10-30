# Background processes

Tengo un proyecto ya configurado con las tecnologías definidas. No necesito que propongas stacks, librerías ni herramientas: esas decisiones ya están tomadas. Lo que necesito es un **plan de implementación** para incorporar procesos en segundo plano, apoyado en una comprensión arquitectónica sólida.

## Concepto arquitectónico que debe regir el plan

Antes de cualquier implementación, el plan debe partir de esta premisa: **en procesamiento en segundo plano, un dato no existe solo como "dato" — existe como un estado**.

La máquina de estados canónica que debe estructurar todo el diseño es:

```
pending → processing → completed
                    ↘ failed
```

Cada transición debe quedar reflejada explícitamente en el plan:

- **pending** — la tarea espera ser ejecutada. El registro se crea *antes* de empezar cualquier trabajo.
- **processing** — se actualiza al inicio de la ejecución, antes de hacer cualquier trabajo real. (Este punto queda cortado en el texto original; el plan debe completar la idea: la marca de "en proceso" precede al trabajo efectivo, de modo que el estado refleje la realidad incluso si el proceso muere a mitad de camino).
- **completed** — transición solo tras finalizar el trabajo con éxito.
- **failed** — transición ante error, con la información necesaria para diagnóstico o reintento.

## Lo que debe entregar el plan

Desarrolla un plan de implementación que cubra, como mínimo:

1. **Modelo de estados** — cómo se representa la máquina de estados en el dominio ya existente: campos, valores permitidos, invariantes y transiciones válidas.
2. **Momento de creación del registro** — garantizar que la tarea se persiste como `pending` antes de cualquier intento de ejecución.
3. **Marcado de inicio** — asegurar que el paso a `processing` ocurre antes del trabajo real, no después.
4. **Transiciones terminales** — condiciones exactas para `completed` y `failed`, incluyendo qué información se guarda en cada caso.
5. **Idempotencia y recuperación** — qué ocurre con tareas que quedan atascadas en `processing` (procesos interrumpidos), cómo se detectan y qué estrategia de reintento o reconciliación se adopta.
6. **Puntos de integración** — dónde encaja este ciclo de vida dentro del flujo actual del proyecto, sin entrar en detalles de tecnología.
7. **Criterios de aceptación** — cómo verificar que cada transición se comporta correctamente en escenarios normales y de fallo.

## Restricciones

- **No entres en tecnologías**: asume que el stack está decidido. Céntrate en arquitectura, estados, flujos y criterios.
- El plan debe ser **accionable por fases**, indicando orden de implementación y dependencias entre pasos.
- Prioriza la **corrección del ciclo de vida** sobre optimizaciones.

---

## Requisitos específicos del proyecto (Extraídos de las imágenes)

Además de lo anterior, el plan debe asegurar el cumplimiento estricto de los siguientes puntos, los cuales definen el alcance técnico y de negocio:

### Qué Debes Hacer

**1. Modelo de datos**
- [ ] Crear una tabla `job_runs` con al menos los campos: `id`, `job_name`, `target_date` (fecha — **obligatorio** para idempotencia por día), `status` (`pending` | `processing` | `completed` | `failed`), `started_at`, `finished_at`, `error_message`, `created_at`.
- [ ] Añadir un índice en (`job_name`, `target_date`) para consultas de idempotencia eficientes.
- [ ] Añadir la migración o instrucción SQL necesaria para crear la tabla en el esquema del monorepo.
- [ ] **No** fusionar `job_runs` con `pipeline_runs` del Hito 6 — capas distintas (ver nota de arquitectura arriba).

**2. Script principal (`scripts/nightly_export.py`)**
- [ ] Resolver `target_date` desde `TARGET_DATE` o por defecto ayer en UTC.
- [ ] El script exporta filas de `telemetry_events` para `target_date` a un CSV en `data/raw/` (p. ej. `telemetry_2025-01-15.csv`), **solo si el archivo no existe**. El CSV es snapshot de backup/auditoría — el pipeline lee desde BD, no este archivo.
- [ ] El script lanza el pipeline de datos como subproceso tras la exportación (comando de referencia: `python -m data.pipelines.telemetry_kpi_daily.run --no-prefect`, o tu entry point CLI del Hito 6).
- [ ] El script escribe en `job_runs` el resultado (estado final + `target_date` + timestamp + error si lo hay).
- [ ] El script es ejecutable desde línea de comandos: `python scripts/nightly_export.py`.

**3. Idempotencia y bloqueo**
- [ ] **Lock vía `processing`**: si ya existe un registro `job_runs` con `status = 'processing'` para `nightly_export`, el script aborta silenciosamente y registra la cancelación. Sin tabla o columna lock aparte.
- [ ] **Idempotencia vía `target_date`**: si ya existe un registro `completed` para (`job_name='nightly_export'`, `target_date`), el script no vuelve a exportar el CSV ni relanza el pipeline. Registra omisión por duplicado. Solo `job_name` sin `target_date` no basta.

**4. Control de estado (`services/`)**
- [ ] Implementar módulo `job_runner` en `services/` con funciones para crear, actualizar y consultar `job_runs` (incl. `has_processing_lock` y `has_completed_for_date`).
- [ ] Cualquier excepción no controlada debe capturarse, actualizar el estado a `failed` con el mensaje de error, y propagar el error al log.
- [ ] Ningún registro puede quedar en estado `processing` tras una ejecución fallida.

**5. Disparador**
- [ ] Configurar el cronjob con `crontab` del SO o un contenedor scheduler dedicado — recomendado en producción.
- [ ] **No** ejecutar el script nocturno dentro del proceso FastAPI (sin `APScheduler`, `@repeat_every` ni hooks lifespan en el servidor API). Un worker separado solo es aceptable si no comparte el hilo principal de la API.
- [ ] Documentar la expresión cron y la decisión de implementación en el cuerpo del PR.
- [ ] Añadir variable de entorno `TARGET_DATE` opcional (`YYYY-MM-DD`) para sobrescribir la fecha objetivo en pruebas sin modificar código.

**6. Observabilidad**
- [ ] Generar logs de ejecución con nivel `INFO` para los eventos normales (inicio, fin, omisión por duplicado) y `ERROR` para excepciones.
- [ ] Cada línea de log incluye timestamp, nombre del job y estado resultante.