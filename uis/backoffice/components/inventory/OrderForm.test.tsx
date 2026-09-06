import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { OrderForm } from "@/components/inventory/OrderForm";
import { ApiRequestError } from "@/lib/api";
import type { InventoryOrderCreate, SKU } from "@/lib/types";

const sneaker: Pick<SKU, "id" | "name"> = {
  id: 1,
  name: "Classic White Sneaker - Size 42",
};

function setup(orderType: "inbound" | "outbound") {
  const onSubmit = vi.fn<(_data: InventoryOrderCreate) => Promise<void>>(() =>
    Promise.resolve(),
  );
  const onClose = vi.fn();
  render(
    <OrderForm
      orderType={orderType}
      sku={sneaker}
      onSubmit={onSubmit}
      onClose={onClose}
    />,
  );
  return { onSubmit, onClose };
}

describe("OrderForm", () => {
  it("renderiza el título según el tipo de orden y el producto", () => {
    setup("inbound");
    expect(screen.getByText("Registrar entrada")).toBeInTheDocument();
    expect(screen.getByText(sneaker.name)).toBeInTheDocument();

    const warehouse = screen.getByLabelText(/Almacén/i);
    expect(warehouse).toHaveValue("los_angeles");
    expect(screen.getByRole("option", { name: "Los Ángeles" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Zaragoza" })).toBeInTheDocument();
  });

  it("no registra la orden con cantidad menor o igual a cero", async () => {
    const { onSubmit } = setup("inbound");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/Cantidad/i), "0");
    await user.click(screen.getByRole("button", { name: "Registrar" }));

    expect(screen.getByText("La cantidad debe ser mayor a 0")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("una orden inbound se envía directamente sin confirmación", async () => {
    const { onSubmit, onClose } = setup("inbound");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/Cantidad/i), "20");
    await user.selectOptions(screen.getByLabelText(/Almacén/i), "zaragoza");
    await user.click(screen.getByRole("button", { name: "Registrar" }));

    expect(onSubmit).toHaveBeenCalledWith({
      sku_id: 1,
      quantity: 20,
      warehouse: "zaragoza",
      order_type: "inbound",
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("una orden outbound pide confirmación antes de enviarse", async () => {
    const { onSubmit } = setup("outbound");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/Cantidad/i), "5");
    await user.click(screen.getByRole("button", { name: "Registrar" }));

    expect(
      screen.getByText(/Estás a punto de registrar una salida de 5 unidades/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Confirmar salida" }));

    expect(onSubmit).toHaveBeenCalledWith({
      sku_id: 1,
      quantity: 5,
      warehouse: "los_angeles",
      order_type: "outbound",
    });
  });

  it("cancela la salida desde la confirmación sin enviar nada", async () => {
    const { onSubmit } = setup("outbound");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/Cantidad/i), "5");
    await user.click(screen.getByRole("button", { name: "Registrar" }));
    const dialog = within(
      screen.getByText(/Estás a punto de registrar una salida/).closest("div")!,
    );
    await user.click(dialog.getByRole("button", { name: "Cancelar" }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("muestra el detail del backend cuando el outbound es rechazado (400)", async () => {
    const onSubmit = vi.fn<(_data: InventoryOrderCreate) => Promise<void>>(() =>
      Promise.reject(
        new ApiRequestError(
          400,
          "Stock insuficiente. Disponible: 3, solicitado: 5.",
          "Stock insuficiente. Disponible: 3, solicitado: 5.",
        ),
      ),
    );
    render(
      <OrderForm
        orderType="outbound"
        sku={sneaker}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />,
    );
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/Cantidad/i), "5");
    await user.click(screen.getByRole("button", { name: "Registrar" }));
    await user.click(screen.getByRole("button", { name: "Confirmar salida" }));

    expect(
      await screen.findByText(/Stock insuficiente\. Disponible: 3, solicitado: 5/),
    ).toBeInTheDocument();
  });
});