"use client";

import { useEffect, useState } from "react";
import {
  createInboundOrder,
  createInventoryProduct,
  createOutboundOrder,
  fetchInventoryOrders,
  fetchInventoryProducts,
  friendlyError,
} from "@/lib/api";
import type {
  InventoryOrderCreate,
  InventoryOrderItem,
  SKU,
  SKUCreate,
} from "@/lib/types";
import {
  INVENTORY_ORDER_TYPES,
  WAREHOUSE_LABELS,
  computeInventoryTotals,
} from "@/lib/types";
import { ProductForm } from "@/components/inventory/ProductForm";
import { OrderForm } from "@/components/inventory/OrderForm";
import { MetricCard } from "@/components/ui/MetricCard";
import { BreakdownCard } from "@/components/ui/BreakdownCard";
import { useAuth } from "@/contexts/AuthContext";

interface OrderTarget {
  sku: Pick<SKU, "id" | "name">;
  orderType: "inbound" | "outbound";
}

export default function InventoryPage() {
  const { token, user } = useAuth();
  const isManager = user?.role === "admin" || user?.role === "manager";

  const [products, setProducts] = useState<SKU[]>([]);
  const [orders, setOrders] = useState<InventoryOrderItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [warehouseFilter, setWarehouseFilter] = useState("");
  const [showProductForm, setShowProductForm] = useState(false);
  const [orderTarget, setOrderTarget] = useState<OrderTarget | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  async function refresh() {
    const [freshProducts, freshOrders] = await Promise.all([
      fetchInventoryProducts(token),
      fetchInventoryOrders(token),
    ]);
    setProducts(freshProducts);
    setOrders(freshOrders);
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [freshProducts, freshOrders] = await Promise.all([
          fetchInventoryProducts(token),
          fetchInventoryOrders(token),
        ]);
        if (cancelled) return;
        setProducts(freshProducts);
        setOrders(freshOrders);
      } catch (err) {
        if (!cancelled) setError(friendlyError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [token, reloadKey]);

  const totals = computeInventoryTotals(products);
  const stockByWarehouse: Record<string, number> = {
    los_angeles: totals.stockByWarehouse.los_angeles ?? 0,
    zaragoza: totals.stockByWarehouse.zaragoza ?? 0,
  };

  const visibleProducts =
    warehouseFilter === ""
      ? products
      : products.filter((product) => product.warehouse === warehouseFilter);

  async function handleCreateProduct(data: SKUCreate) {
    await createInventoryProduct(data, token);
    await refresh();
  }

  async function handleOrder(data: InventoryOrderCreate) {
    const { sku_id, quantity, warehouse } = data;
    if (data.order_type === "inbound") {
      await createInboundOrder({ sku_id, quantity, warehouse }, token);
    } else {
      await createOutboundOrder({ sku_id, quantity, warehouse }, token);
    }
    await refresh();
  }

  const selectClass =
    "rounded-lg border border-white/10 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none";

  return (
    <>
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Inventario</h1>
          <p className="mt-2 text-slate-400">
            Stock en tiempo real por almacén y registro de órdenes inbound/outbound.
          </p>
        </div>
        {isManager && (
          <button
            onClick={() => setShowProductForm(true)}
            className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500"
          >
            + Nuevo producto
          </button>
        )}
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="SKUs totales" value={totals.totalSkus} />
        <MetricCard title="Stock total" value={totals.totalStock} />
        <div className="lg:col-span-2">
          <BreakdownCard
            title="Stock por almacén"
            items={stockByWarehouse}
            labels={WAREHOUSE_LABELS}
          />
        </div>
      </div>

      <div className="mb-6 flex flex-wrap gap-4">
        <select
          aria-label="Filtrar por almacén"
          value={warehouseFilter}
          onChange={(e) => setWarehouseFilter(e.target.value)}
          className={selectClass}
        >
          <option value="">Todos los almacenes</option>
          {Object.entries(WAREHOUSE_LABELS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-rose-400/20 bg-rose-500/10 p-5">
          <p className="text-sm font-medium text-rose-300">Error: {error}</p>
          <button
            onClick={() => setReloadKey((k) => k + 1)}
            className="mt-3 rounded-lg bg-rose-500/20 px-4 py-2 text-sm font-medium text-rose-200 transition hover:bg-rose-500/30"
          >
            Reintentar
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
        </div>
      ) : (
        <>
          <section aria-label="Productos">
            <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/60">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-white/10 bg-slate-800/50">
                  <tr>
                    <th className="px-4 py-3 font-medium text-slate-300">Producto</th>
                    <th className="px-4 py-3 font-medium text-slate-300">SKU</th>
                    <th className="px-4 py-3 font-medium text-slate-300">Almacén</th>
                    <th className="px-4 py-3 font-medium text-slate-300">Stock</th>
                    <th className="px-4 py-3 font-medium text-slate-300">Total</th>
                    {isManager && (
                      <th className="px-4 py-3 font-medium text-slate-300">Acciones</th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {visibleProducts.map((product) => (
                    <tr key={product.id} className="transition hover:bg-white/5">
                      <td className="px-4 py-3">
                        <div className="font-medium text-white">{product.name}</div>
                      </td>
                      <td className="px-4 py-3 text-slate-300">{product.sku_code}</td>
                      <td className="px-4 py-3 text-slate-300">
                        {WAREHOUSE_LABELS[product.warehouse] ?? product.warehouse}
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-block rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-300">
                          {product.current_stock_by_warehouse[product.warehouse] ?? 0}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-block rounded-full bg-cyan-500/20 px-2 py-0.5 text-xs font-medium text-cyan-300">
                          {product.current_stock}
                        </span>
                      </td>
                      {isManager && (
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() =>
                                setOrderTarget({ sku: product, orderType: "inbound" })
                              }
                              className="rounded-lg bg-emerald-600/20 px-3 py-1 text-xs font-medium text-emerald-300 transition hover:bg-emerald-600/40"
                            >
                              Entrada
                            </button>
                            <button
                              onClick={() =>
                                setOrderTarget({ sku: product, orderType: "outbound" })
                              }
                              className="rounded-lg bg-cyan-600/20 px-3 py-1 text-xs font-medium text-cyan-300 transition hover:bg-cyan-600/40"
                            >
                              Salida
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                  {visibleProducts.length === 0 && (
                    <tr>
                      <td
                        colSpan={isManager ? 6 : 5}
                        className="px-4 py-12 text-center text-slate-500"
                      >
                        No se encontraron productos
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-label="Órdenes registradas" className="mt-8">
            <h2 className="mb-3 text-lg font-semibold text-white">Historial de órdenes</h2>
            <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/60">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-white/10 bg-slate-800/50">
                  <tr>
                    <th className="px-4 py-3 font-medium text-slate-300">Tipo</th>
                    <th className="px-4 py-3 font-medium text-slate-300">Producto</th>
                    <th className="px-4 py-3 font-medium text-slate-300">Almacén</th>
                    <th className="px-4 py-3 font-medium text-slate-300">Cantidad</th>
                    <th className="px-4 py-3 font-medium text-slate-300">Usuario</th>
                    <th className="px-4 py-3 font-medium text-slate-300">Fecha</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {orders.map((item) => (
                    <tr
                      key={`${item.order_type}-${item.id}`}
                      className="transition hover:bg-white/5"
                    >
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                            item.order_type === "inbound"
                              ? "bg-emerald-500/20 text-emerald-300"
                              : "bg-cyan-500/20 text-cyan-300"
                          }`}
                        >
                          {INVENTORY_ORDER_TYPES[item.order_type] ?? item.order_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-300">{item.product_name}</td>
                      <td className="px-4 py-3 text-slate-300">
                        {WAREHOUSE_LABELS[item.warehouse] ?? item.warehouse}
                      </td>
                      <td className="px-4 py-3 text-slate-300">{item.quantity}</td>
                      <td className="px-4 py-3 text-xs text-slate-500">{item.user_uuid}</td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {new Date(item.created_at).toLocaleString("es-ES")}
                      </td>
                    </tr>
                  ))}
                  {orders.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                        Aún no hay órdenes registradas
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {showProductForm && (
        <ProductForm
          onSubmit={handleCreateProduct}
          onClose={() => setShowProductForm(false)}
        />
      )}

      {orderTarget && (
        <OrderForm
          key={`${orderTarget.orderType}-${orderTarget.sku.id}`}
          orderType={orderTarget.orderType}
          sku={orderTarget.sku}
          onSubmit={handleOrder}
          onClose={() => setOrderTarget(null)}
        />
      )}
    </>
  );
}