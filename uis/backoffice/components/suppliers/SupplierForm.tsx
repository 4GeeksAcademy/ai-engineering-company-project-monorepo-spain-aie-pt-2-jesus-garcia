"use client";

import { useState } from "react";
import type { Supplier, SupplierCreate, SupplierUpdate } from "@/lib/types";
import {
  SUPPLIER_CATEGORIES,
  SUPPLIER_STATUSES,
} from "@/lib/types";
import { friendlyError } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface SupplierFormProps {
  supplier?: Supplier | null;
  onSubmit: (data: SupplierCreate | SupplierUpdate) => Promise<void>;
  onClose: () => void;
}

export function SupplierForm({ supplier, onSubmit, onClose }: SupplierFormProps) {
  const [name, setName] = useState(supplier?.name ?? "");
  const [country, setCountry] = useState(supplier?.country ?? "USA");
  const [categories, setCategories] = useState<string[]>(supplier?.categories ?? []);
  const [ratePerShipment, setRatePerShipment] = useState(
    supplier?.rate_per_shipment?.toString() ?? ""
  );
  const [status, setStatus] = useState(supplier?.status ?? "active");
  const [serviceZone, setServiceZone] = useState(supplier?.service_zone ?? "");
  const [contactEmail, setContactEmail] = useState(supplier?.contact_email ?? "");
  const [notes, setNotes] = useState(supplier?.notes ?? "");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pendingSubmit, setPendingSubmit] = useState<
    SupplierCreate | SupplierUpdate | null
  >(null);

  function toggleCategory(cat: string) {
    setCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  }

  function validate(): boolean {
    const newErrors: Record<string, string> = {};
    if (!name.trim()) newErrors.name = "El nombre es obligatorio";
    if (!country) newErrors.country = "El país es obligatorio";
    if (categories.length === 0) newErrors.categories = "Selecciona al menos una categoría";
    if (!ratePerShipment || parseFloat(ratePerShipment) <= 0) {
      newErrors.rate = "La tarifa debe ser mayor a 0";
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setPendingSubmit({
      name: name.trim(),
      country,
      categories,
      rate_per_shipment: parseFloat(ratePerShipment),
      status,
      service_zone: serviceZone.trim() || null,
      contact_email: contactEmail.trim() || null,
      notes: notes.trim() || null,
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
          <h2 className="mb-4 text-xl font-bold text-white">
            {supplier ? "Editar proveedor" : "Nuevo proveedor"}
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-slate-400">Nombre *</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="Nombre del proveedor"
              />
              {errors.name && <p className="mt-1 text-xs text-rose-400">{errors.name}</p>}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm text-slate-400">País *</label>
                <select
                  value={country}
                  onChange={(e) => setCountry(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                >
                  <option value="USA">🇺🇸 USA</option>
                  <option value="Spain">🇪🇸 España</option>
                </select>
                {errors.country && <p className="mt-1 text-xs text-rose-400">{errors.country}</p>}
              </div>

              <div>
                <label className="mb-1 block text-sm text-slate-400">Estado *</label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                >
                  {Object.entries(SUPPLIER_STATUSES).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-400">Tarifa por envío *</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">
                  {country === "USA" ? "$" : "€"}
                </span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={ratePerShipment}
                  onChange={(e) => setRatePerShipment(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-slate-800 py-2 pl-8 pr-3 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                  placeholder="0.00"
                />
              </div>
              {errors.rate && <p className="mt-1 text-xs text-rose-400">{errors.rate}</p>}
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-400">Categorías *</label>
              <div className="flex flex-wrap gap-2">
                {Object.entries(SUPPLIER_CATEGORIES).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleCategory(key)}
                    className={`rounded-full px-3 py-1 text-xs transition ${
                      categories.includes(key)
                        ? "bg-cyan-500/20 text-cyan-300 ring-1 ring-cyan-500/50"
                        : "bg-slate-700 text-slate-400 hover:bg-slate-600"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {errors.categories && (
                <p className="mt-1 text-xs text-rose-400">{errors.categories}</p>
              )}
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-400">Zona de servicio</label>
              <input
                type="text"
                value={serviceZone}
                onChange={(e) => setServiceZone(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="ej. West Coast, Península Ibérica"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-400">Email de contacto</label>
              <input
                type="email"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="contacto@empresa.com"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-400">Notas</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="Observaciones del equipo de operaciones"
              />
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
            {supplier ? "Guardar cambios" : "Crear proveedor"}
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingSubmit !== null}
        title={supplier ? "Guardar cambios" : "Crear proveedor"}
        message={`Estás a punto de guardar al proveedor "${
          name.trim() || "sin nombre"
        }". ¿Confirmas los datos?`}
        confirmLabel={supplier ? "Guardar cambios" : "Crear proveedor"}
        loading={loading}
        onConfirm={handleConfirm}
        onCancel={() => setPendingSubmit(null)}
      />
    </div>
  );
}
