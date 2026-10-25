import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePagination } from "@/hooks/usePagination";

function makeItems(count: number): number[] {
  return Array.from({ length: count }, (_, index) => index + 1);
}

describe("usePagination", () => {
  it("muestra como máximo 25 elementos por defecto", () => {
    const { result } = renderHook(() => usePagination(makeItems(30)));

    expect(result.current.page).toBe(1);
    expect(result.current.pageSize).toBe(25);
    expect(result.current.total).toBe(30);
    expect(result.current.totalPages).toBe(2);
    expect(result.current.pageItems).toHaveLength(25);
    expect(result.current.start).toBe(1);
    expect(result.current.end).toBe(25);
  });

  it("navega a la siguiente página y ajusta el rango", () => {
    const { result } = renderHook(() => usePagination(makeItems(30)));

    act(() => result.current.setPage(2));

    expect(result.current.page).toBe(2);
    expect(result.current.pageItems).toEqual([26, 27, 28, 29, 30]);
    expect(result.current.start).toBe(26);
    expect(result.current.end).toBe(30);
  });

  it("acota la página al rango válido", () => {
    const { result } = renderHook(() => usePagination(makeItems(30)));

    act(() => result.current.setPage(99));
    expect(result.current.page).toBe(2);

    act(() => result.current.setPage(0));
    expect(result.current.page).toBe(1);
  });

  it("vuelve a la primera página si la lista se acorta", () => {
    const { result, rerender } = renderHook(
      ({ items }: { items: number[] }) => usePagination(items),
      { initialProps: { items: makeItems(30) } },
    );

    act(() => result.current.setPage(2));
    expect(result.current.page).toBe(2);

    rerender({ items: makeItems(10) });

    expect(result.current.page).toBe(1);
    expect(result.current.totalPages).toBe(1);
    expect(result.current.pageItems).toHaveLength(10);
  });

  it("vuelve a la primera página al cambiar la clave de reseteo (filtros)", () => {
    const { result, rerender } = renderHook(
      ({ resetKey }: { resetKey: string }) =>
        usePagination(makeItems(60), { resetKey }),
      { initialProps: { resetKey: "" } },
    );

    act(() => result.current.setPage(3));
    expect(result.current.page).toBe(3);

    rerender({ resetKey: "status=open" });

    expect(result.current.page).toBe(1);
    expect(result.current.pageItems[0]).toBe(1);
  });

  it("cambiar el tamaño de página recalcula el total y vuelve a la página 1", () => {
    const { result } = renderHook(() => usePagination(makeItems(30)));

    act(() => result.current.setPage(2));
    act(() => result.current.setPageSize(10));

    expect(result.current.page).toBe(1);
    expect(result.current.pageSize).toBe(10);
    expect(result.current.totalPages).toBe(3);
    expect(result.current.pageItems).toHaveLength(10);
  });

  it("expone un estado vacío coherente", () => {
    const { result } = renderHook(() => usePagination([]));

    expect(result.current.total).toBe(0);
    expect(result.current.totalPages).toBe(1);
    expect(result.current.pageItems).toEqual([]);
    expect(result.current.start).toBe(0);
    expect(result.current.end).toBe(0);
  });
});
