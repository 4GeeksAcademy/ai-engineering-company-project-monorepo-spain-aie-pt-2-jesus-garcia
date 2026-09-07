import { describe, expect, it } from "vitest";
import {
  INVENTORY_ORDER_TYPES,
  WAREHOUSE_LABELS,
  computeInventoryTotals,
} from "@/lib/types";

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