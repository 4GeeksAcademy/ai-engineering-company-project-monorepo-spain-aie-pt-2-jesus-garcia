# Auditoría de rendimiento — TrackFlow

> Auditoría evidencia-based con **Lighthouse 12.3** sobre Chrome real (motor idéntico a la pestaña Lighthouse de DevTools).
> Aplicación: monorepo TrackFlow — frontends `uis/website` (sitio corporativo) y `uis/backoffice` (panel de operaciones).
> Artefactos: `audit/before/*.png`, `audit/after/*.png`, JSON.gz y HTML por ejecución.

## Método

Solo se auditan las páginas que importan (una ejecución en la home no representa un dashboard con carga de datos):

| App | Página | Por qué |
|---|---|---|
| website | `/` home | Mayor tráfico y componente LCP (`truck-hero.jpg`). Se audita **desktop y mobile**. |
| website | `/application` | Página compleja del flujo de conversión (formulario multi-paso). |
| backoffice | `/incidents` | Vista densa: 4 tarjetas, 4 filtros, tabla de 95 incidencias, modales. |
| backoffice | `/inventory` | Dashboard de operaciones: métricas, desglose, tabla de productos + historial de órdenes. |

- Servidores: builds de **producción** (`next build && next start`, no `next dev`), backend FastAPI con datos seed (95 incidencias) y sesión autenticada inyectada en localStorage (`trackflow_token`).
- Tooling reproducible: `scripts/perf-audit/run.mjs` (Chrome real + Lighthouse programático).

## Scores baseline

| App | Página | Modo | Performance | Accessibility | Best Practices | SEO |
|---|---|---|---|---|---|---|
| website | `/` | desktop | 100 | 100 | 100 | 100 |
| website | `/` | mobile | 100 | 100 | 100 | 100 |
| website | `/application` | desktop | 100 | 100 | 100 | 100 |
| backoffice | `/incidents` | desktop | 100 | **91** | 100 | 100 |
| backoffice | `/inventory` | desktop | 100 | **94** | 100 | 100 |

### Core Web Vitals y señales de servidor (baseline)

| Página | Modo | LCP | CLS | INP | TTFB | FCP | TBT |
|---|---|---|---|---|---|---|---|
| website `/` | desktop | 0.30 s | 0.019 | — | 1 ms | 174 ms | 0 ms |
| website `/` | mobile | 0.63 s | 0.000 | — | 2 ms | 628 ms | 0 ms |
| website `/application` | desktop | 0.18 s | 0.000 | — | 1 ms | 175 ms | 0 ms |
| backoffice `/incidents` | desktop | 0.30 s | 0.023 | — | 2 ms | 173 ms | 0 ms |
| backoffice `/inventory` | desktop | 0.30 s | 0.010 | — | 2 ms | 173 ms | 0 ms |

**Benchmarks objetivo** (nota del CTO): Performance ≥ 90, LCP < 2.5 s, CLS < 0.1, INP < 200 ms, TTFB bajo. Todos se cumplen en baseline; el trabajo se centró en corregir las auditorías fallidas (oportunidades reales) y la accesibilidad.

## Issues y causa raíz

### 1. Imagen hero (LCP) cargada con `loading="lazy"` (website home)

- **Síntoma:** audit `lcp-lazy-loaded` con score 0.5 en desktop y mobile; el flag desaparece tras el fix.
- **Causa raíz:** `uis/website/components/HeroSection.tsx` usaba `next/image` **sin `priority`**, por lo que el bundle aplicaba el default `loading="lazy"` al elemento que define el LCP. Sin `sizes`, el `srcset` servía además imágenes más grandes que el contenedor (`max-w-md` ≈ 448 px).
- **Fix:** `priority`, `sizes="(max-width: 768px) 90vw, 448px"` y `quality={80}` en el hero.

### 2. Activos fuente sobredimensionados (website)

- **Síntoma:** `logo.png` de **213 KB a 872×872** renderizado a 48 px (Header) y 56/128 px (backoffice auth); `truck-hero.jpg` de **326 KB a 3275×3568** para un contenedor de ~448 px.
- **Causa raíz:** los assets de `public/` se añadieron sin pensar en el tamaño de render. Un PNG de 872 px y un JPEG de 11.7 MP pagan en peso de descarga y caché sin beneficio visual.
- **Fix:** recompresión con `sips` (nativo macOS): `logo.png` → 256×256 (~46 KB, −78 %) en **ambos** frontends (copia idéntica); `truck-hero.jpg` → 1101×1200/q75 (~186 KB, −43 %). Se mantienen los mismos nombres de archivo: **zero-cambio de código**.

### 3. Contraste insuficiente en el backoffice (fondo oscuro)

- **Síntoma:** audit `color-contrast` con score **0** en `/incidents` (102 elementos) y `/inventory` (27 elementos); Accessibility 91 y 94.
- **Causa raíz:** texto pequeño (`text-xs`, `text-sm`) en `text-slate-500` (~4.05:1) y `text-slate-400` (~4.66:1) sobre `slate-950` sale por debajo del umbral AA (4.5:1). Concentrado en:
  - `/incidents`: descripciones de incidencias `td > div.line-clamp-1` (95), labels de tarjetas de estado (4), contador de filas (1).
  - `/inventory`: celdas `text-slate-500` del historial (25), estados vacíos de tablas (2).
  - Componentes compartidos: `Sidebar` (email), `MetricCard`, y los CTAs `bg-cyan-600` con texto blanco (3.7:1 — falla AA).
- **Fix:** subir los textos a `text-slate-300` y los botones primarios a `bg-cyan-700` (≥ 5.0:1) con hover `bg-cyan-600`. Cambios quirúrgicos de clase en archivos afectados.

### 4. Filtros `<select>` sin nombre accesible (backoffice `/incidents`)

- **Síntoma:** audit `select-name` fallando en 4 elementos.
- **Causa raíz:** los 4 `<select>` de filtros (estado, origen, sede, categoría) no tenían `aria-label` ni `<label>`. El label visual era un texto separado sin asociación.
- **Fix:** `aria-label` descriptivo en cada select ("Filtrar por estado/origen/sede/categoría").

### 5. Jerarquía de headings rota (backoffice `/inventory`)

- **Síntoma:** audit `heading-order` fallando (1 elemento).
- **Causa raíz:** `BreakdownCard` rendereza su título como `<h3>` pero la página no tiene `<h2>` previo (el `h2` "Historial de órdenes" está después).
- **Fix:** el título de `BreakdownCard` pasa a `<h2>` (respeta la jerarquía h1 → h2 en ambas páginas).

### 6. Duplicado: lógica fetch + estado loading/error copiada en 3 páginas

- **Síntoma:** ~25 líneas casi idénticas (`useState` data/loading/error + `useEffect` con `cancelled` + `friendlyError`) en `/incidents`, `/suppliers` e `/inventory`.
- **Causa raíz:** copy-paste del patrón inicial; cada página lo reimplementa con casos de cancelación y reintento.
- **Fix (refactor):** **Custom Hook `useAsyncData`** en `uis/backoffice/hooks/useAsyncData.ts` (ver Refactor candidates). Integrado en `/inventory` (doble fetch en paralelo products + orders).

### 7. Duplicado: markup de spinner de carga en 2 apps

- **Síntoma:** mismo bloque `h-10 w-10 animate-spin rounded-full border-4 border-slate-600 border-t-cyan-400` en `uis/website/app/loading.tsx` y `uis/backoffice/app/(protected)/layout.tsx`.
- **Causa raíz:** patrón copiado entre frontends sin fuente única.
- **Fix (refactor):** **componente compartido `shared/components/LoadingSpinner.ts`** consumido por ambas apps (ver Refactor candidates).

## Refactor candidates

| # | Duplicado | Ubicaciones | Extracción | Estado |
|---|---|---|---|---|
| 1 | Estado fetch `data/loading/error` + efecto | `app/(protected)/inventory/page.tsx`, `incidents/page.tsx`, `suppliers/page.tsx` | `uis/backoffice/hooks/useAsyncData.ts` (`loader`, `deps`, `mapError`, `reload`) | ✅ Integrado en `/inventory`. `/incidents` y `/suppliers` quedan como callers elegibles. |
| 2 | Spinner de carga | `uis/website/app/loading.tsx`, `uis/backoffice/app/(protected)/layout.tsx` | `shared/components/LoadingSpinner.ts` (raíz del monorepo, alias `@shared/*`) | ✅ Integrado en ambas apps. |

**Nota técnica sobre el directorio `shared/`:** el monorepo declara `shared/` como código compartido en la raíz. Turbopack no transpila `.tsx` (JSX) fuera de la raíz de cada app, pero sí módulos `.ts`; por eso `LoadingSpinner` usa `createElement` en un `.ts` y los tsconfigs de ambas apps mapean `react` → sus `@types` locales (ver `tsconfig.json` de cada app).

## Agent skills

- `core-web-vitals`, `performance` y `web-perf` (Cloudflare): **no instaladas** en el monorepo (solo existe `validate-commit`). No se instalaron desde fuentes externas; se siguió el flujo de auditoría manual:
  - `validate-commit` (skill local) → usada para el flujo pre-commit: typecheck, lint, build y revisión de cambios.
  - `browser-automation` (skill local) → disponible para verificación de render; en esta auditoría la verificación se hizo con el propio runner de Lighthouse (requests `/api/*` 200 + recuento de nodos DOM).
- Clasificación de los fixes: todos los aplicados son **required fixes** (auditorías fallidas o duplicados); se documentan como *suggestion* los residuales de **oportunidad** (legend: `uses-responsive-images` ~12 KiB y `legacy-javascript` ~14 KiB de polyfills para navegadores antiguos), que no justifican cambio dado el stack objetivo.