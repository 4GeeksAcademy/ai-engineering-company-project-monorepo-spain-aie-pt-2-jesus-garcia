"use client";

import { PAGE_SIZE_OPTIONS } from "@/hooks/usePagination";
import type { RefObject } from "react";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  /** Sustantivo usado en el texto y en las etiquetas accesibles ("proveedores"). */
  label: string;
  /** Elemento que se lleva a la vista al cambiar de página (la tabla). */
  scrollTargetRef?: RefObject<HTMLElement | null>;
  pageSizeOptions?: readonly number[];
}

const navButtonClass =
  "rounded-md border border-white/10 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-slate-800 disabled:hover:text-slate-300";

const pageButtonClass =
  "min-w-8 rounded-md border px-2 py-1.5 text-xs font-medium transition";

function pageWindow(page: number, totalPages: number): (number | "gap")[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const pages = new Set<number>([1, totalPages, page]);
  for (let offset = 1; offset <= 2; offset += 1) {
    pages.add(page - offset);
    pages.add(page + offset);
  }
  if (page <= 4) {
    [2, 3, 4, 5].forEach((value) => pages.add(value));
  }
  if (page >= totalPages - 3) {
    [totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1].forEach(
      (value) => pages.add(value),
    );
  }

  const sorted = [...pages]
    .filter((value) => value >= 1 && value <= totalPages)
    .sort((a, b) => a - b);

  const window: (number | "gap")[] = [];
  sorted.forEach((value, index) => {
    const previous = sorted[index - 1];
    if (previous !== undefined && value - previous > 1) {
      window.push("gap");
    }
    window.push(value);
  });
  return window;
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  label,
  scrollTargetRef,
  pageSizeOptions = PAGE_SIZE_OPTIONS,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  const showSizeSelector =
    onPageSizeChange !== undefined &&
    total > Math.min(...pageSizeOptions);

  function changePage(next: number) {
    onPageChange(next);
    const target = scrollTargetRef?.current;
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-400">
      <p aria-live="polite">
        {total === 0 ? (
          "Sin resultados"
        ) : (
          <>
            Mostrando{" "}
            <span className="font-medium text-slate-200">
              {start}–{end}
            </span>{" "}
            de {total} {label}
          </>
        )}
      </p>

      <div className="flex flex-wrap items-center gap-3">
        {showSizeSelector && (
          <label className="flex items-center gap-2 text-xs text-slate-400">
            <span>Filas por página</span>
            <select
              aria-label={`Filas por página en ${label}`}
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
              className="rounded-md border border-white/10 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
            >
              {pageSizeOptions.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        )}

        {totalPages > 1 && (
          <nav
            aria-label={`Paginación de ${label}`}
            className="flex flex-wrap items-center gap-1"
          >
            <button
              type="button"
              onClick={() => changePage(page - 1)}
              disabled={page <= 1}
              className={navButtonClass}
            >
              ‹ Anterior
            </button>

            {pageWindow(page, totalPages).map((value, index) =>
              value === "gap" ? (
                <span key={`gap-${index}`} className="px-1 text-slate-500">
                  …
                </span>
              ) : (
                <button
                  key={value}
                  type="button"
                  onClick={() => changePage(value)}
                  aria-current={value === page ? "page" : undefined}
                  aria-label={`Página ${value} de ${totalPages}`}
                  className={`${pageButtonClass} ${
                    value === page
                      ? "border-cyan-500 bg-cyan-600 text-white"
                      : "border-white/10 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
                  }`}
                >
                  {value}
                </button>
              ),
            )}

            <button
              type="button"
              onClick={() => changePage(page + 1)}
              disabled={page >= totalPages}
              className={navButtonClass}
            >
              Siguiente ›
            </button>
          </nav>
        )}
      </div>
    </div>
  );
}
