"use client";

import { useState } from "react";
import type { InventoryOrderCreate, SKU } from "@/lib/types";
import { WAREHOUSE_LABELS } from "@/lib/types";
import { ApiRequestError, friendlyError } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface OrderFormProps {
  orderType: "inbound" | "outbound";
  sku: Pick<SKU, "id" | "name">;
  onSubmit: (data: InventoryOrderCreate) => Promise<void>;
  onClose: () => void;
}

const TITLES: Record<OrderFormProps["orderType"], string> = {
  inbound: "Registrar entrada",
  outbound: "Registrar salida",
};

export function OrderForm({ orderType, sku, onSubmit, onClose }: OrderFormProps) {
  const [quantity, setQuantity] = useState("");
  const [warehouse, setWarehouse] = useState("los_angeles");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pendingSubmit, setPendingSubmit] = useState<InventoryOrderCreate | null>(
    null,
  );

  const numericQuantity = parseInt(quantity, 10);

  function buildPayload(): InventoryOrderCreate {
    return {
      sku_id: sku.id,
      quantity: numericQuantity,
      warehouse,
      order_type: orderType,
    };
  }

  function validate(): boolean {
    const newErrors: Record<string, string> = {};
    if (!Number.isInteger(numericQuantity) || numericQuantity <= 0) {
      newErrors.quantity = "La cantidad debe ser mayor a 0";
    }
    if (!warehouse) newErrors.warehouse = "El almacén es obligatorio";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  async function doSubmit(payload: InventoryOrderCreate) {
    setLoading(true);
    try {
      await onSubmit(payload);
      onClose();
    } catch (err) {
      setErrors({
        submit:
          err instanceof ApiRequestError && typeof err.detail === "string"
            ? err.detail
            : friendlyError(err),
      });
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    const payload = buildPayload();
    if (orderType === "outbound") {
      setPendingSubmit(payload);
    } else {
      doSubmit(payload);
    }
  }

  async function handleConfirm() {
    if (!pendingSubmit) return;
    await doSubmit(pendingSubmit);
  }

  const isOutbound = orderType === "outbound";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl border border-white/10 bg-slate-900 shadow-xl">
        <div className="overflow-y-auto p-6">
          <h2 className="mb-1 text-xl font-bold text-white">{TITLES[orderType]}</h2>
          <p className="mb-4 text-sm text-slate-400">{sku.name}</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="order-quantity"
                  className="mb-1 block text-sm text-slate-400"
                >
                  Cantidad *
                </label>
                <input
                  id="order-quantity"
                  type="number"
                  step="1"
                  min="1"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                  placeholder="0"
                />
                {errors.quantity && (
                  <p className="mt-1 text-xs text-rose-400">{errors.quantity}</p>
                )}
              </div>

              <div>
                <label
                  htmlFor="order-warehouse"
                  className="mb-1 block text-sm text-slate-400"
                >
                  Almacén *
                </label>
                <select
                  id="order-warehouse"
                  value={warehouse}
                  onChange={(e) => setWarehouse(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                >
                  {Object.entries(WAREHOUSE_LABELS).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
                {errors.warehouse && (
                  <p className="mt-1 text-xs text-rose-400">{errors.warehouse}</p>
                )}
              </div>
            </div>

            {errors.submit && (
              <p className="text-sm text-rose-400">{errors.submit}</p>
            )}
          </form>
        </div>

        <div className="flex justify-end gap-3 border-t border-white/10 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-slate-400 transition hover:bg-white/5 hover:text-white"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={loading}
            onClick={handleSubmit}
            className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:opacity-50"
          >
            Registrar
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingSubmit !== null}
        title={TITLES[orderType]}
        message={`Estás a punto de registrar ${isOutbound ? "una salida" : "una entrada"} de ${
          numericQuantity
        } unidades de "${sku.name}" en el almacén ${warehouse}.`}
        confirmLabel={isOutbound ? "Confirmar salida" : "Confirmar"}
        loading={loading}
        onConfirm={handleConfirm}
        onCancel={() => setPendingSubmit(null)}
      />
    </div>
  );
}