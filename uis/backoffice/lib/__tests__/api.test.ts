import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiRequestError,
  createInboundOrder,
  createInventoryProduct,
  createOutboundOrder,
  fetchInventoryOrders,
  fetchInventoryProduct,
  fetchInventoryProducts,
  friendlyError,
} from "@/lib/api";
import type { SKU } from "@/lib/types";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 400 ? "Bad Request" : "OK",
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

const sampleSku: SKU = {
  id: 1,
  name: "Classic White Sneaker - Size 42",
  sku_code: "CLT-SNK-W-42",
  warehouse: "los_angeles",
  current_stock: 47,
  current_stock_by_warehouse: { los_angeles: 47, zaragoza: 0 },
};

describe("fetchInventoryProducts", () => {
  it("hace GET a /api/inventory/products con Bearer y devuelve los SKUs", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, [sampleSku]));

    const result = await fetchInventoryProducts("tok123");

    expect(fetchMock).toHaveBeenCalledWith("/api/inventory/products", {
      headers: { Authorization: "Bearer tok123" },
    });
    expect(result).toEqual([sampleSku]);
  });
});

describe("fetchInventoryProduct", () => {
  it("hace GET al detalle con el id y Bearer", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, sampleSku));

    const result = await fetchInventoryProduct(1, "tok123");

    expect(fetchMock).toHaveBeenCalledWith("/api/inventory/products/1", {
      headers: { Authorization: "Bearer tok123" },
    });
    expect(result).toEqual(sampleSku);
  });
});

describe("createInventoryProduct", () => {
  it("hace POST con JSON y Bearer", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { ...sampleSku, id: 2 }));
    const data = {
      name: "Classic White Sneaker - Size 42",
      sku_code: "CLT-SNK-W-42",
      warehouse: "los_angeles",
    };

    const result = await createInventoryProduct(data, "tok123");

    expect(fetchMock).toHaveBeenCalledWith("/api/inventory/products", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer tok123",
      },
      body: JSON.stringify(data),
    });
    expect(result).toEqual({ ...sampleSku, id: 2 });
  });
});

describe("fetchInventoryOrders", () => {
  it("hace GET a /api/inventory/orders con Bearer", async () => {
    const orders = [
      {
        id: 1,
        order_type: "inbound" as const,
        sku_id: 1,
        product_name: "Classic White Sneaker - Size 42",
        warehouse: "zaragoza",
        quantity: 20,
        user_uuid: "a1b2c3d4",
        created_at: "2025-06-01T10:30:00Z",
      },
    ];
    fetchMock.mockResolvedValue(jsonResponse(200, orders));

    const result = await fetchInventoryOrders("tok123");

    expect(fetchMock).toHaveBeenCalledWith("/api/inventory/orders", {
      headers: { Authorization: "Bearer tok123" },
    });
    expect(result).toEqual(orders);
  });
});

describe("createInboundOrder", () => {
  it("hace POST a /orders/inbound con sku_id, quantity y warehouse", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { id: 1 }));
    const data = { sku_id: 1, quantity: 20, warehouse: "zaragoza" };

    await createInboundOrder(data, "tok123");

    expect(fetchMock).toHaveBeenCalledWith("/api/inventory/orders/inbound", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer tok123",
      },
      body: JSON.stringify(data),
    });
  });
});

describe("createOutboundOrder", () => {
  it("hace POST a /orders/outbound con sku_id, quantity y warehouse", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { id: 2 }));
    const data = { sku_id: 1, quantity: 5, warehouse: "los_angeles" };

    await createOutboundOrder(data, "tok123");

    expect(fetchMock).toHaveBeenCalledWith("/api/inventory/orders/outbound", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer tok123",
      },
      body: JSON.stringify(data),
    });
  });

  it("cuando el backend devuelve 400, propaga el detail de stock insuficiente", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(400, {
        detail: "Stock insuficiente para SKU 'CLT-SNK-W-42'. Disponible: 5, solicitado: 10.",
      }),
    );

    const promise = createOutboundOrder(
      { sku_id: 1, quantity: 10, warehouse: "los_angeles" },
      "tok123",
    );

    await expect(promise).rejects.toBeInstanceOf(ApiRequestError);
    await expect(promise).rejects.toThrow(
      "Stock insuficiente para SKU 'CLT-SNK-W-42'. Disponible: 5, solicitado: 10.",
    );
  });
});

describe("friendlyError", () => {
  it("para el mensaje de outbound 400 usa el detail del backend, no el genérico", () => {
    const err = new ApiRequestError(
      400,
      "Stock insuficiente. Disponible: 3, solicitado: 5.",
      "Stock insuficiente. Disponible: 3, solicitado: 5.",
    );
    expect(friendlyError(err)).toBe("La solicitud no es válida. Revisa los datos enviados.");
    expect(err.detail).toBe("Stock insuficiente. Disponible: 3, solicitado: 5.");
  });
});