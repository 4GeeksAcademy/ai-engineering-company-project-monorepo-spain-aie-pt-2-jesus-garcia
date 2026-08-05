"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { fetchSuppliers, ApiRequestError } from "@/lib/api";
import type { Supplier } from "@/lib/types";
import {
  SUPPLIER_CATEGORIES,
  SUPPLIER_STATUSES,
  COUNTRY_FLAGS,
} from "@/lib/types";

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [countryFilter, setCountryFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchSuppliers({
          country: countryFilter || undefined,
          status: statusFilter || undefined,
          category: categoryFilter || undefined,
        });
        if (!cancelled) setSuppliers(data);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiRequestError) {
            setError(err.message);
          } else {
            setError("Error al cargar proveedores");
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [countryFilter, statusFilter, categoryFilter]);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-6 lg:p-10">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">
            Directorio de proveedores
          </h1>
          <p className="mt-2 text-slate-400">
            Gestión centralizada de carriers, suministros y servicios para
            operaciones en USA y España.
          </p>
        </div>

        <div className="mb-6 flex flex-wrap gap-4">
          <select
            value={countryFilter}
            onChange={(e) => setCountryFilter(e.target.value)}
            className="rounded-lg border border-white/10 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <option value="">Todos los países</option>
            <option value="USA">🇺🇸 USA</option>
            <option value="Spain">🇪🇸 España</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-white/10 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <option value="">Todos los estados</option>
            <option value="active">Activo</option>
            <option value="suspended">Suspendido</option>
          </select>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="rounded-lg border border-white/10 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <option value="">Todas las categorías</option>
            {Object.entries(SUPPLIER_CATEGORIES).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <div className="mb-6 rounded-xl border border-rose-400/20 bg-rose-500/10 p-5">
            <p className="text-sm font-medium text-rose-300">
              Error: {error}
            </p>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/60">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-slate-800/50">
                <tr>
                  <th className="px-4 py-3 font-medium text-slate-300">
                    Nombre
                  </th>
                  <th className="px-4 py-3 font-medium text-slate-300">
                    País
                  </th>
                  <th className="px-4 py-3 font-medium text-slate-300">
                    Categorías
                  </th>
                  <th className="px-4 py-3 font-medium text-slate-300">
                    Tarifa
                  </th>
                  <th className="px-4 py-3 font-medium text-slate-300">
                    Estado
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {suppliers.map((supplier) => (
                  <tr
                    key={supplier.id}
                    className="transition hover:bg-white/5"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-white">
                        {supplier.name}
                      </div>
                      {supplier.contact_email && (
                        <div className="text-xs text-slate-500">
                          {supplier.contact_email}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-slate-300">
                        {COUNTRY_FLAGS[supplier.country] ?? ""}{" "}
                        {supplier.country}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {supplier.categories.map((cat) => (
                          <span
                            key={cat}
                            className="inline-block rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-300"
                          >
                            {SUPPLIER_CATEGORIES[cat] ?? cat}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {supplier.currency === "USD" ? "$" : "€"}
                      {supplier.rate_per_shipment.toFixed(2)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                          supplier.status === "active"
                            ? "bg-emerald-500/20 text-emerald-300"
                            : "bg-amber-500/20 text-amber-300"
                        }`}
                      >
                        {SUPPLIER_STATUSES[supplier.status] ?? supplier.status}
                      </span>
                    </td>
                  </tr>
                ))}
                {suppliers.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-12 text-center text-slate-500"
                    >
                      No se encontraron proveedores
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {!loading && suppliers.length > 0 && (
          <p className="mt-4 text-sm text-slate-500">
            {suppliers.length} proveedor{suppliers.length !== 1 ? "es" : ""}
          </p>
        )}
      </main>
    </div>
  );
}
