"use client";

import { useCallback, useMemo, useState } from "react";

export const PAGE_SIZE_OPTIONS = [10, 25, 50] as const;
export const DEFAULT_PAGE_SIZE = 25;

interface UsePaginationOptions {
  initialPageSize?: number;
  /** Cambiar este valor devuelve la paginación a la primera página (p. ej. al cambiar filtros). */
  resetKey?: string | number;
}

export function usePagination<T>(
  items: readonly T[],
  {
    initialPageSize = DEFAULT_PAGE_SIZE,
    resetKey = "",
  }: UsePaginationOptions = {},
) {
  const [page, setPageState] = useState(1);
  const [pageSize, setPageSizeState] = useState(initialPageSize);
  const [prevResetKey, setPrevResetKey] = useState(resetKey);

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Ajuste de estado durante el render (patrón recomendado por React) para que un
  // cambio de filtros o una lista más corta nunca deje la tabla en una página vacía.
  const nextPage = prevResetKey !== resetKey ? 1 : Math.min(page, totalPages);
  if (nextPage !== page || prevResetKey !== resetKey) {
    setPrevResetKey(resetKey);
    setPageState(nextPage);
  }

  const currentPage = Math.min(page, totalPages);

  const setPage = useCallback(
    (next: number) => {
      setPageState(Math.max(1, Math.min(next, totalPages)));
    },
    [totalPages],
  );

  const setPageSize = useCallback((next: number) => {
    setPageSizeState(next);
    setPageState(1);
  }, []);

  const resetPage = useCallback(() => setPageState(1), []);

  const pageItems = useMemo(
    () => items.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [items, currentPage, pageSize],
  );

  const start = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const end = Math.min(currentPage * pageSize, total);

  return {
    page: currentPage,
    setPage,
    pageSize,
    setPageSize,
    total,
    totalPages,
    pageItems,
    start,
    end,
    resetPage,
  };
}
