import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Pagination } from "@/components/ui/Pagination";

describe("Pagination", () => {
  it("muestra el rango visible y el total", () => {
    render(
      <Pagination
        page={2}
        pageSize={25}
        total={80}
        onPageChange={vi.fn()}
        label="proveedores"
      />,
    );

    expect(
      screen.getByText(
        (_, element) =>
          element?.tagName === "P" &&
          element.textContent === "Mostrando 26–50 de 80 proveedores",
      ),
    ).toBeInTheDocument();
  });

  it("deshabilita anterior en la primera página y siguiente en la última", () => {
    const { rerender } = render(
      <Pagination
        page={1}
        pageSize={25}
        total={80}
        onPageChange={vi.fn()}
        label="incidencias"
      />,
    );

    expect(screen.getByRole("button", { name: "‹ Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Siguiente ›" })).toBeEnabled();

    rerender(
      <Pagination
        page={4}
        pageSize={25}
        total={80}
        onPageChange={vi.fn()}
        label="incidencias"
      />,
    );

    expect(screen.getByRole("button", { name: "‹ Anterior" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Siguiente ›" })).toBeDisabled();
  });

  it("notifica el cambio de página al pulsar un número", async () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={1}
        pageSize={10}
        total={35}
        onPageChange={onPageChange}
        label="productos"
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Página 3 de 4" }));
    expect(onPageChange).toHaveBeenCalledWith(3);

    await userEvent.click(screen.getByRole("button", { name: "Siguiente ›" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("marca la página actual con aria-current", () => {
    render(
      <Pagination
        page={2}
        pageSize={10}
        total={35}
        onPageChange={vi.fn()}
        label="productos"
      />,
    );

    expect(screen.getByRole("button", { name: "Página 2 de 4" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("button", { name: "Página 1 de 4" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("oculta la navegación cuando solo hay una página", () => {
    render(
      <Pagination
        page={1}
        pageSize={25}
        total={3}
        onPageChange={vi.fn()}
        label="órdenes"
      />,
    );

    expect(
      screen.queryByRole("navigation", { name: "Paginación de órdenes" }),
    ).not.toBeInTheDocument();
  });

  it("muestra el selector de tamaño solo con más filas que la página más pequeña", async () => {
    const onPageSizeChange = vi.fn();
    const { rerender } = render(
      <Pagination
        page={1}
        pageSize={25}
        total={8}
        onPageChange={vi.fn()}
        onPageSizeChange={onPageSizeChange}
        label="filas"
      />,
    );

    expect(
      screen.queryByLabelText("Filas por página en filas"),
    ).not.toBeInTheDocument();

    rerender(
      <Pagination
        page={1}
        pageSize={25}
        total={60}
        onPageChange={vi.fn()}
        onPageSizeChange={onPageSizeChange}
        label="filas"
      />,
    );

    await userEvent.selectOptions(
      screen.getByLabelText("Filas por página en filas"),
      "50",
    );
    expect(onPageSizeChange).toHaveBeenCalledWith(50);
  });
});
