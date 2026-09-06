import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InventoryPage from "@/app/(protected)/inventory/page";
import * as api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { InventoryOrderItem, SKU } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchInventoryProducts: vi.fn(),
    fetchInventoryOrders: vi.fn(),
    createInventoryProduct: vi.fn(),
    createInboundOrder: vi.fn(),
    createOutboundOrder: vi.fn(),
  };
});

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

const mockUseAuth = vi.mocked(useAuth);
const mockFetchProducts = vi.mocked(api.fetchInventoryProducts);
const mockFetchOrders = vi.mocked(api.fetchInventoryOrders);
const mockCreateOutbound = vi.mocked(api.createOutboundOrder);

const sku1: SKU = {
  id: 1,
  name: "Classic White Sneaker - Size 42",
  sku_code: "CLT-SNK-W-42",
  warehouse: "los_angeles",
  current_stock: 47,
  current_stock_by_warehouse: { los_angeles: 47, zaragoza: 0 },
};

const sku2: SKU = {
  id: 2,
  name: "Running Trainer - Size 40",
  sku_code: "RUN-TRN-40",
  warehouse: "zaragoza",
  current_stock: 20,
  current_stock_by_warehouse: { los_angeles: 0, zaragoza: 20 },
};

const order: InventoryOrderItem = {
  id: 1,
  order_type: "inbound",
  sku_id: 1,
  product_name: "Classic White Sneaker - Size 42",
  warehouse: "zaragoza",
  quantity: 20,
  user_uuid: "a1b2c3d4-e5f6",
  created_at: "2025-06-01T10:30:00Z",
};

function mockRole(role: "admin" | "manager" | "user") {
  mockUseAuth.mockReturnValue({
    token: "test-token",
    user: {
      id: "1",
      email: "ops@trackflow.com",
      is_active: true,
      role,
      created_at: "",
    },
    isLoading: false,
    isAuthenticated: true,
    sessionError: null,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    retryValidation: vi.fn(),
  } as ReturnType<typeof useAuth>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockFetchProducts.mockResolvedValue([sku1, sku2]);
  mockFetchOrders.mockResolvedValue([order]);
});

describe("InventoryPage", () => {
  it("muestra la cabecera, los resúmenes y los datos de productos y órdenes", async () => {
    mockRole("manager");
    render(<InventoryPage />);

    expect(await screen.findByText("Inventario")).toBeInTheDocument();
    expect(screen.getByText("+ Nuevo producto")).toBeInTheDocument();

    expect(screen.getByText("SKUs totales")).toBeInTheDocument();
    expect(screen.getByText("Stock total")).toBeInTheDocument();
    expect(screen.getByText("Stock por almacén")).toBeInTheDocument();

    const products = await screen.findByRole("region", { name: "Productos" });
    expect(await within(products).findByText(sku1.name)).toBeInTheDocument();
    expect(within(products).getByText(sku1.sku_code)).toBeInTheDocument();
    expect(within(products).getByText(sku2.name)).toBeInTheDocument();

    const orders = await screen.findByRole("region", { name: "Órdenes registradas" });
    expect(within(orders).getByText("20")).toBeInTheDocument();
    expect(within(orders).getByText("a1b2c3d4-e5f6")).toBeInTheDocument();
  });

  it("un usuario con role user no puede crear ni registrar órdenes", async () => {
    mockRole("user");
    render(<InventoryPage />);

    expect(await screen.findByText("Inventario")).toBeInTheDocument();
    expect(screen.queryByText("+ Nuevo producto")).not.toBeInTheDocument();

    const products = await screen.findByRole("region", { name: "Productos" });
    await within(products).findByText(sku1.name);
    expect(within(products).queryByRole("button", { name: "Entrada" })).not.toBeInTheDocument();
    expect(within(products).queryByRole("button", { name: "Salida" })).not.toBeInTheDocument();
  });

  it("filtra la tabla de productos por almacén", async () => {
    mockRole("manager");
    render(<InventoryPage />);

    const products = await screen.findByRole("region", { name: "Productos" });
    await within(products).findByText(sku1.name);

    const filter = screen.getByLabelText("Filtrar por almacén");
    await userEvent.selectOptions(filter, "los_angeles");

    expect(within(products).getByText(sku1.name)).toBeInTheDocument();
    expect(within(products).queryByText(sku2.name)).not.toBeInTheDocument();
  });

  it("abre el modal de salida desde la acción de la fila", async () => {
    mockRole("manager");
    render(<InventoryPage />);

    const products = await screen.findByRole("region", { name: "Productos" });
    await within(products).findByText(sku1.name);
    const row = within(products).getByText(sku1.name).closest("tr")!;

    await userEvent.click(within(row).getByRole("button", { name: "Salida" }));

    expect(await screen.findByText("Registrar salida")).toBeInTheDocument();
  });

  it("muestra el detail del backend cuando un outbound es rechazado (400)", async () => {
    mockRole("manager");
    mockCreateOutbound.mockRejectedValue(
      new api.ApiRequestError(
        400,
        "Stock insuficiente para SKU 'CLT-SNK-W-42'. Disponible: 5, solicitado: 10.",
        "Stock insuficiente para SKU 'CLT-SNK-W-42'. Disponible: 5, solicitado: 10.",
      ),
    );
    render(<InventoryPage />);

    const products = await screen.findByRole("region", { name: "Productos" });
    await within(products).findByText(sku1.name);
    const row = within(products).getByText(sku1.name).closest("tr")!;

    await userEvent.click(within(row).getByRole("button", { name: "Salida" }));
    await userEvent.type(await screen.findByLabelText(/Cantidad/i), "10");
    await userEvent.click(screen.getByRole("button", { name: "Registrar" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmar salida" }));

    expect(
      await screen.findByText(
        "Stock insuficiente para SKU 'CLT-SNK-W-42'. Disponible: 5, solicitado: 10.",
      ),
    ).toBeInTheDocument();
    expect(mockCreateOutbound).toHaveBeenCalledWith(
      { sku_id: 1, quantity: 10, warehouse: "los_angeles" },
      "test-token",
    );
  });
});