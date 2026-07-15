---
description: "Convenciones de desarrollo del Talent Tracker (People & Talent recruitment pipeline)"
globs: "uis/talent-pipeline-tracker/**/*.{ts,tsx}"
alwaysApply: true
---

# Talent Tracker — Reglas de desarrollo

## API Client (`lib/api.ts`)

- Toda llamada HTTP debe usar la función `request<T>` con tipado genérico.
- Usar `buildUrl(path, params)` para construir URLs con query params; omitir valores `undefined` o `""`.
- Los errores HTTP deben lanzar `ApiRequestError` con `status` y `detail`.
- Toda función expuesta debe ser `async` con tipado de retorno explícito.
- Endpoints disponibles:

  | Método | Función | Ruta |
  |---|---|---|
  | GET | `getRecords` | `/records?status=&stage=&search=&page=&limit=` |
  | POST | `createRecord` | `/records` |
  | GET | `getRecord` | `/records/{id}` |
  | PATCH | `patchRecord` | `/records/{id}` |
  | PUT | `updateRecord` | `/records/{id}` |
  | DELETE | `deleteRecord` | `/records/{id}` |
  | POST | `addNote` | `/records/{id}/notes` |
  | DELETE | `deleteNote` | `/records/{id}/notes/{note_id}` |

## Hooks

- `useCandidates(params)` — Fetch con filtros, maneja `loading`/`error`/`data`. Usar flag `cancelled` para evitar actualizaciones tras desmontar.
- `useDebounce(value, 300)` — Debounce de 300ms para el input de búsqueda.
- `useCandidateNotes(recordId)` — Fetch/crear/eliminar notas con estado local.
- Los hooks deben devolver siempre `{ data, loading, error, refetch }` como interfaz mínima.

## Filtros y URL (`CandidateFilters.tsx`)

- Los filtros (status, stage, search) deben sincronizarse con `URLSearchParams`.
- El cambio de filtro debe resetear `page` a 1 (`params.delete("page")`).
- La búsqueda por nombre/email debe usar `useDebounce` (300ms) antes de actualizar la URL.
- Los selects de status/stage deben recorrer `CANDIDATE_STATUS_VALUES` y `CANDIDATE_STAGE_VALUES` desde `constants.ts`.

## Componentes y estados

- Todo componente que use estado o efectos debe llevar `"use client"`.
- `CandidateList` debe manejar 3 estados: `loading` → `LoadingSpinner`, `error` → `ErrorMessage` con `onRetry`, vacío → `EmptyState`.
- `CandidateCard` es una fila de tabla: nombre, puesto, `StatusBadge`, `StageBadge`, fecha.
- `CandidateDetail` se renderiza dentro de `SidePanel` (panel deslizable desde la derecha).
- `CandidateForm` usa `<dialog>` nativo de HTML. Llamar `showModal()`/`close()` según prop `open`.
  - Resetear `key` con `candidate?.id ?? "new"` para reiniciar estado interno.
- Las notas (`NoteList` + `NoteForm`) viven dentro del panel de detalle.

## Paleta de colores (Tailwind v4)

- Fondo general: `bg-slate-950`, paneles: `bg-slate-900`, bordes: `border-white/10`
- Acento primario: `cyan-400`/`cyan-500`
- Estados: `received` → gray, `in_progress` → blue, `selected` → green, `discarded` → red
- Etapas: `pending` → gray, `review` → amber, `personal_interview` → blue, `technical_interview` → purple, `offer_presented` → green

## Manejo de errores

- No hay fallos silenciosos. Todo `catch` debe mostrar un mensaje visible.
- En operaciones de formulario: mostrar feedback tipo `success`/`error` con timeout antes de cerrar.
- Los errores de API se propagan como `ApiRequestError` con `status` y `detail`.

## Reglas generales

- Sin comentarios en código.
- Imports con alias `@/` (ej. `@/lib/api`, `@/components/ui/LoadingSpinner`).
- Tipos e interfaces en `lib/types.ts`; constantes y enums en `lib/constants.ts`.
- `CandidateStatus` y `CandidateStage` son tipos literal (`"received" | "in_progress" | …`).
- `page` y `limit` se pasan como números, la URL los serializa automáticamente.
