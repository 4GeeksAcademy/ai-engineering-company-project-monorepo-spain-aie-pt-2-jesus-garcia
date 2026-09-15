"use client";

import { useState } from "react";
import type { SKUCreate } from "@/lib/types";
import { WAREHOUSE_LABELS } from "@/lib/types";
import { friendlyError } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface ProductFormProps {
  onSubmit: (data: SKUCreate) => Promise<void>;
  onClose: () => void;
}

export function ProductForm({ onSubmit, onClose }: ProductFormProps) {
  const [name, setName] = useState("");
  const [skuCode, setSkuCode] = useState("");
  const [warehouse, setWarehouse] = useState("los_angeles");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pendingSubmit, setPendingSubmit] = useState<SKUCreate | null>(null);

  function validate(): boolean {
    const newErrors: Record<string, string> = {};
    if (!name.trim()) newErrors.name = "El nombre es obligatorio";
    if (!skuCode.trim()) newErrors.skuCode = "El código SKU es obligatorio";
    if (!warehouse) newErrors.warehouse = "El almacén es obligatorio";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setPendingSubmit({
      name: name.trim(),
      sku_code: skuCode.trim(),
      warehouse,
    });
  }

  async function handleConfirm() {
    if (!pendingSubmit) return;
    setLoading(true);
    try {
      await onSubmit(pendingSubmit);
      onClose();
    } catch (err) {
      setErrors({ submit: friendlyError(err) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl border border-white/10 bg-slate-900 shadow-xl">
        <div className="overflow-y-auto p-6">
          <h2 className="mb-4 text-xl font-bold text-white">Nuevo producto</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="product-name"
                className="mb-1 block text-sm text-slate-400"
              >
                Nombre *
              </label>
              <input
                id="product-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="Nombre del producto"
              />
              {errors.name && (
                <p className="mt-1 text-xs text-rose-400">{errors.name}</p>
              )}
            </div>

            <div>
              <label
                htmlFor="product-sku"
                className="mb-1 block text-sm text-slate-400"
              >
                Código SKU *
              </label>
              <input
                id="product-sku"
                type="text"
                value={skuCode}
                onChange={(e) => setSkuCode(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="ej. CLT-SNK-W-42"
              />
              {errors.skuCode && (
                <p className="mt-1 text-xs text-rose-400">{errors.skuCode}</p>
              )}
            </div>

            <div>
              <label
                htmlFor="product-warehouse"
                className="mb-1 block text-sm text-slate-400"
              >
                Almacén *
              </label>
              <select
                id="product-warehouse"
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
            Crear producto
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingSubmit !== null}
        title="Crear producto"
        message={`Estás a punto de crear el producto "${
          name.trim() || "sin nombre"
        }". ¿Confirmas los datos?`}
        confirmLabel="Confirmar"
        loading={loading}
        onConfirm={handleConfirm}
        onCancel={() => setPendingSubmit(null)}
      />
    </div>
  );
}