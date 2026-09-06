import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProductForm } from "@/components/inventory/ProductForm";
import type { SKUCreate } from "@/lib/types";

function setup() {
  const onSubmit = vi.fn<(_data: SKUCreate) => Promise<void>>(() => Promise.resolve());
  const onClose = vi.fn();
  render(<ProductForm onSubmit={onSubmit} onClose={onClose} />);
  return { onSubmit, onClose };
}

describe("ProductForm", () => {
  it("renderiza el modal de alta de producto con sus campos", () => {
    setup();

    expect(screen.getByText("Nuevo producto")).toBeInTheDocument();
    expect(screen.getByLabelText(/Nombre/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Código SKU/i)).toBeInTheDocument();

    const warehouse = screen.getByLabelText(/Almacén/i);
    expect(warehouse).toHaveValue("los_angeles");
    expect(screen.getByRole("option", { name: "Los Ángeles" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Zaragoza" })).toBeInTheDocument();
  });

  it("no envía datos si falta el nombre o el código SKU", async () => {
    const { onSubmit } = setup();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Crear producto" }));

    expect(screen.getByText("El nombre es obligatorio")).toBeInTheDocument();
    expect(screen.getByText("El código SKU es obligatorio")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("abre la confirmación y envía el payload al confirmar", async () => {
    const { onSubmit } = setup();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/Nombre/i), "Classic White Sneaker - Size 42");
    await user.type(screen.getByLabelText(/Código SKU/i), "CLT-SNK-W-42");
    await user.selectOptions(screen.getByLabelText(/Almacén/i), "zaragoza");
    await user.click(screen.getByRole("button", { name: "Crear producto" }));

    expect(
      screen.getByText(/Classic White Sneaker - Size 42/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: "Classic White Sneaker - Size 42",
      sku_code: "CLT-SNK-W-42",
      warehouse: "zaragoza",
    });
  });

  it("cierra el modal al cancelar", async () => {
    const { onClose } = setup();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});