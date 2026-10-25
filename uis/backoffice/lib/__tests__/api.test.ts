import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiRequestError,
  createInboundOrder,
  createInventoryProduct,
  createOutboundOrder,
  fetchInventoryOrders,
  fetchInventoryProduct,
  fetchInventoryProducts,
  fetchTelemetryReport,
  friendlyError,
} from "@/lib/api";
import type { SKU, TelemetryReport } from "@/lib/types";

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
        user_email: "ops@trackflow.com",
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
const telemetryReport: TelemetryReport = {
  period: { from: "2026-06-14T00:00:00Z", to: "2026-06-16T00:00:00Z" },
  metrics: {
    events_per_day: [
      { date: "2026-06-14", event_type: "page_view", event_count: 3 },
    ],
    error_rate_by_day: [
      { date: "2026-06-14", event_count: 3, error_count: 1, error_rate: 0.3333 },
    ],
    errors_by_type: [
      { date: "2026-06-14", event_type: "login_failed", error_count: 1 },
    ],
    latency_per_day: [
      { date: "2026-06-14", avg_ms: 30, p50_ms: 30, p95_ms: 40.8, sample_count: 2 },
    ],
    auth_failure_rate: [
      { date: "2026-06-14", failed: 1, succeeded: 2, failure_rate: 0.3333 },
    ],
  },
};

describe("fetchTelemetryReport", () => {
  it("hace GET a /api/telemetry/report con el periodo indicado", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, telemetryReport));

    const result = await fetchTelemetryReport({
      start_date: "2026-06-14T00:00:00Z",
      end_date: "2026-06-16T00:00:00Z",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/telemetry/report?start_date=2026-06-14T00%3A00%3A00Z&end_date=2026-06-16T00%3A00%3A00Z",
      { headers: {} },
    );
    expect(result).toEqual(telemetryReport);
  });

  it("omite los parámetros cuando no se indica periodo", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, telemetryReport));

    await fetchTelemetryReport();

    expect(fetchMock).toHaveBeenCalledWith("/api/telemetry/report", {
      headers: {},
    });
  });
});
