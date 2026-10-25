import { describe, expect, it } from "vitest";
import {
  INVENTORY_ORDER_TYPES,
  WAREHOUSE_LABELS,
  computeInventoryTotals,
  computeTelemetrySummary,
} from "@/lib/types";
import type { TelemetryMetrics } from "@/lib/types";

describe("mapeos de inventario", () => {
  it("define las etiquetas de los dos almacenes", () => {
    expect(WAREHOUSE_LABELS.los_angeles).toBe("Los Ángeles");
    expect(WAREHOUSE_LABELS.zaragoza).toBe("Zaragoza");
  });

  it("define las etiquetas de tipos de orden", () => {
    expect(INVENTORY_ORDER_TYPES.inbound).toBe("Entrada");
    expect(INVENTORY_ORDER_TYPES.outbound).toBe("Salida");
  });
});

describe("computeInventoryTotals", () => {
  it("devuelve ceros para una lista vacía", () => {
    expect(computeInventoryTotals([])).toEqual({
      totalSkus: 0,
      totalStock: 0,
      stockByWarehouse: {},
    });
  });

  it("suma el stock global y desglosado por almacén", () => {
    const products = [
      {
        current_stock: 47,
        current_stock_by_warehouse: { los_angeles: 47, zaragoza: 0 },
      },
      {
        current_stock: 20,
        current_stock_by_warehouse: { los_angeles: 0, zaragoza: 20 },
      },
    ] as Parameters<typeof computeInventoryTotals>[0];

    expect(computeInventoryTotals(products)).toEqual({
      totalSkus: 2,
      totalStock: 67,
      stockByWarehouse: { los_angeles: 47, zaragoza: 20 },
    });
  });
});
const emptyTelemetryMetrics: TelemetryMetrics = {
  events_per_day: [],
  error_rate_by_day: [],
  errors_by_type: [],
  latency_per_day: [],
  auth_failure_rate: [],
};

describe("computeTelemetrySummary", () => {
  it("devuelve ceros y nulos para un informe vacío", () => {
    expect(computeTelemetrySummary(emptyTelemetryMetrics)).toEqual({
      totalEvents: 0,
      errorRate: null,
      avgLatency: null,
      authFailureRate: null,
    });
  });

  it("pondera errores, latencia y fallos de login por sus denominadores", () => {
    const summary = computeTelemetrySummary({
      events_per_day: [
        { date: "2026-06-14", event_type: "page_view", event_count: 10 },
        { date: "2026-06-15", event_type: "page_view", event_count: 5 },
      ],
      error_rate_by_day: [
        { date: "2026-06-14", event_count: 10, error_count: 1, error_rate: 0.1 },
        { date: "2026-06-15", event_count: 5, error_count: 2, error_rate: 0.4 },
      ],
      errors_by_type: [],
      latency_per_day: [
        { date: "2026-06-14", avg_ms: 100, p50_ms: 100, p95_ms: 120, sample_count: 2 },
        { date: "2026-06-15", avg_ms: 40, p50_ms: 40, p95_ms: 40, sample_count: 1 },
      ],
      auth_failure_rate: [
        { date: "2026-06-14", failed: 2, succeeded: 2, failure_rate: 0.5 },
        { date: "2026-06-15", failed: 1, succeeded: 0, failure_rate: 1 },
      ],
    });

    expect(summary.totalEvents).toBe(15);
    expect(summary.errorRate).toBeCloseTo(0.2);
    expect(summary.avgLatency).toBeCloseTo(80);
    expect(summary.authFailureRate).toBeCloseTo(0.6);
  });
});
