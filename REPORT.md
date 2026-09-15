# Reporte de rendimiento — TrackFlow

## Cambios aplicados

### Rendimiento (website)

1. **LCP hero** — `uis/website/components/HeroSection.tsx`: `next/image` con `priority`, `sizes="(max-width: 768px) 90vw, 448px"` y `quality={80}`. Elimina el lazy-load del elemento LCP (`lcp-lazy-loaded` resuelto).
2. **Activos fuente** — recompresión con `sips`:
   - `logo.png` (website + backoffice): 872×872 **213 KB** → 256×256 **46 KB** (−78 %).
   - `truck-hero.jpg` (website): 3275×3568 **326 KB** → 1101×1200/q75 **186 KB** (−43 %).

### Accesibilidad (backoffice)

3. **Contraste AA** — textos `text-slate-500/400` → `text-slate-300` en tablas, tarjetas, sidebar y contadores; CTAs primarios `bg-cyan-600` (3.7:1) → `bg-cyan-700` (≥ 5.0:1). Archivos: `incidents/page.tsx`, `inventory/page.tsx`, `Sidebar.tsx`, `MetricCard.tsx`, `StatusFlowModal.tsx`.
4. **Selects accesibles** — `aria-label` en los 4 filtros de `/incidents` (`select-name` resuelto).
5. **Jerarquía de headings** — `BreakdownCard` pasa de `h3` a `h2` (`heading-order` resuelto en `/inventory`).

### Refactor (doble fuente de abstracción compartida)

6. **Custom Hook `useAsyncData`** — `uis/backoffice/hooks/useAsyncData.ts` (`loader`, `deps`, `mapError`, `reload`). Extrae el patrón duplicado `data/loading/error` de 3 páginas; **integrado en `/inventory`** (doble fetch products + orders en paralelo). `incidents` y `suppliers` quedan como callers elegibles.
7. **Componente compartido `LoadingSpinner`** — `shared/components/LoadingSpinner.ts` (código compartido de la raíz, alias `@shared/*`). Reemplaza el markup duplicado en `uis/website/app/loading.tsx` y `uis/backoffice/app/(protected)/layout.tsx`.

### Infra por el camino

8. `turbopack.root` → raíz del monorepo en ambos `next.config.ts` (resolución de imports fuera de la app) y `@source` de Tailwind v4 apuntando a `shared/` en ambos `globals.css`.

## Score delta

| App | Página | Modo | Metric | Before | After | Δ |
|---|---|---|---|---|---|---|
| website | `/` | desktop | Performance | 100 | 100 | — |
| website | `/` | desktop | LCP | 0.30 s | 0.20 s | **−31 %** |
| website | `/` | desktop | CLS | 0.019 | 0.000 | −0.019 |
| website | `/` | desktop | `lcp-lazy-loaded` | 0.5 | 1.0 | **resuelto** |
| website | `/` | mobile | Performance | 100 | 100 | — |
| website | `/application` | desktop | Performance | 100 | 100 | — |
| backoffice | `/incidents` | desktop | Accessibility | **91** | **100** | **+9** |
| backoffice | `/incidents` | desktop | Performance | 100 | 100 | — |
| backoffice | `/inventory` | desktop | Accessibility | **94** | **100** | **+6** |
| backoffice | `/inventory` | desktop | Performance | 100 | 100 | — |

Auditorías adicionales resueltas en el backoffice: `select-name` (4), `heading-order` (1) y `color-contrast` (102 + 27 elementos) pasan a verde. Las 5 ejecuciones posteriores quedan en **100/100/100/100**.

## Mayor impacto

- **Imagen LCP con `priority` + activos re-comprimidos**: acorta la latencia de pintado (LCP desktop home 0.30 → 0.20 s) aunque el Performance ya fuese 100; recorta ~300 KB de transferencia en las páginas públicas.
- **Accesibilidad del backoffice**: los cambios de contraste y etiquetado llevan `incidents` 91 → 100 y `inventory` 94 → 100. Son los fixes de mayor impacto real sobre usuarios (lectura de tablas densas en fondo oscuro).
- **Refactor de estado fetch**: el hook eliminó ~25 líneas duplicadas por página y centraliza el manejo de cancelación y errores; impacto marginal en score (esperado, según el criterio de puntuación de Lighthouse), pero impacto real en mantenimiento.

## Residuales documentados (suggestion, no bloquean)

- `uses-responsive-images`: ~12 KiB de ahorro teórico en el hero (servido a `w=640` vs 448 px ideales). Requiere insertar raw steps personalizados en `sizes`/config; se descarta como oportunidad menor.
- `legacy-javascript` + `legacy-javascript-insight`: ~14 KiB de polyfills (JS destinado a navegadores antiguos). No es relevante para el stack objetivo.
- `network-dependency-tree-insight` / `render-blocking-insight`: diagnósticos informativos de la versión 12.3 de Lighthouse, sin acción accionable.
- `dom-size` (1248 nodos en `/incidents`): informativo; la tabla de 95 incidencias lo justifica.

## Checklist de validación

- [x] Lighthouse **before/after** en ambos frontends con capturas en `audit/before/` y `audit/after/` (PNG full-page + JSON.gz + HTML).
- [x] `AUDIT.md` explica el **porqué** de cada score (causa raíz), no solo los flags.
- [x] Al menos una abstracción compartida — en realidad **dos**: Custom Hook `useAsyncData` (integrado) y componente `LoadingSpinner` (integrado en ambas apps).
- [x] `REPORT.md` muestra mejora medible en ≥1 score por frontend (website: LCP −31 %; backoffice: A11y +9 y +6 hasta 100).
- [x] Sin rewrite arquitectónico: cambios quirúrgicos (clases, atributos, 1 hook y 1 componente).
- [x] Monorepo sigue funcionando: typecheck raíz OK, lint y build de ambos frontends OK, **32 tests** de backoffice en verde (Vitest).
- [x] Evidencia commit-eada: `audit/`, `AUDIT.md`, `REPORT.md`, fixes y refactors.

## Cómo reproducir

```bash
# 1) Backend con datos + seed admin
cd services/api && source venv/bin/activate && python seed_users.py
uvicorn app.main:app --port 8000

# 2) Builds de producción
(cd uis/website && npm run build && npx next start -p 3000) &
(cd uis/backoffice && npm run build && npx next start -p 3001) &

# 3) Auditoría (Chrome real + Lighthouse)
cd scripts/perf-audit && npm install
node run.mjs before   # -> audit/before/
node run.mjs after    # -> audit/after/
```