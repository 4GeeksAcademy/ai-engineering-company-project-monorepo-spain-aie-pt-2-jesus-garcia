"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { fetchSuppliers, createSupplier, updateSupplier, deleteSupplier, ApiRequestError } from "@/lib/api";
import type { Supplier, SupplierCreate, SupplierUpdate } from "@/lib/types";
import {
  SUPPLIER_CATEGORIES,
  SUPPLIER_STATUSES,
  COUNTRY_FLAGS,
} from "@/lib/types";
import { SupplierForm } from "@/components/suppliers/SupplierForm";

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [countryFilter, setCountryFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [searchInput, setSearchInput] = useState<string>("");
  const debouncedSearch = useDebounce(searchInput, 300);

  const [showForm, setShowForm] = useState(false);
  const [editingSupplier, setEditingSupplier] = useState<Supplier | null>(null);

  const [confirmDelete, setConfirmDelete] = useState<Supplier | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  async function refresh() {
    const fresh = await fetchSuppliers({
      country: countryFilter || undefined,
      status: statusFilter || undefined,
      category: categoryFilter || undefined,
      search: debouncedSearch || undefined,
    });
    setSuppliers(fresh);
  }

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
          search: debouncedSearch || undefined,
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
  }, [countryFilter, statusFilter, categoryFilter, debouncedSearch]);

  function handleCreateNew() {
    setEditingSupplier(null);
    setShowForm(true);
  }

  function handleEdit(supplier: Supplier) {
    setEditingSupplier(supplier);
    setShowForm(true);
  }

  async function handleSubmit(data: SupplierCreate | SupplierUpdate) {
    if (editingSupplier) {
      await updateSupplier(editingSupplier.id, data as SupplierUpdate);
    } else {
      await createSupplier(data as SupplierCreate);
    }
    await refresh();
  }

  async function handleToggleStatus(supplier: Supplier) {
    const newStatus = supplier.status === "active" ? "suspended" : "active";
    setActionLoading(supplier.id);
    try {
      await updateSupplier(supplier.id, { status: newStatus });
      await refresh();
    } catch {
      setError("Error al cambiar estado");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleConfirmDelete() {
    if (!confirmDelete) return;
    setActionLoading(confirmDelete.id);
    try {
      await deleteSupplier(confirmDelete.id);
      setConfirmDelete(null);
      await refresh();
    } catch {
      setError("Error al eliminar proveedor");
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-6 lg:p-10">
        <div className="mb-8 flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white">
              Directorio de proveedores
            </h1>
            <p className="mt-2 text-slate-400">
              Gestión centralizada de carriers, suministros y servicios para
              operaciones en USA y España.
            </p>
          </div>
          <button
            onClick={handleCreateNew}
            className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500"
          >
            + Nuevo proveedor
          </button>
        </div>

        <div className="mb-6 flex flex-wrap gap-4">
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
              />
            </svg>
            <input
              type="text"
              placeholder="Buscar por nombre..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="rounded-lg border border-white/10 bg-slate-800 py-2 pl-10 pr-4 text-sm text-slate-200 placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
            />
          </div>

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
                  <th className="px-4 py-3 font-medium text-slate-300">
                    Acciones
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
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleEdit(supplier)}
                          className="rounded p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white"
                          title="Editar"
                        >
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleToggleStatus(supplier)}
                          disabled={actionLoading === supplier.id}
                          className={`rounded p-1.5 transition ${
                            supplier.status === "active"
                              ? "text-amber-400 hover:bg-amber-500/20"
                              : "text-emerald-400 hover:bg-emerald-500/20"
                          } disabled:opacity-50`}
                          title={supplier.status === "active" ? "Suspender" : "Reactivar"}
                        >
                          {supplier.status === "active" ? (
                            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25v13.5m-7.5-13.5v13.5" />
                            </svg>
                          ) : (
                            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                            </svg>
                          )}
                        </button>
                        <button
                          onClick={() => setConfirmDelete(supplier)}
                          disabled={actionLoading === supplier.id}
                          className="rounded p-1.5 text-slate-400 transition hover:bg-rose-500/20 hover:text-rose-400 disabled:opacity-50"
                          title="Eliminar"
                        >
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {suppliers.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
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

      {showForm && (
        <SupplierForm
          supplier={editingSupplier}
          onSubmit={handleSubmit}
          onClose={() => setShowForm(false)}
        />
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-xl border border-white/10 bg-slate-900 p-6 shadow-xl">
            <h3 className="text-lg font-bold text-white">Eliminar proveedor</h3>
            <p className="mt-2 text-sm text-slate-400">
              ¿Estás seguro de que quieres eliminar <span className="font-medium text-white">{confirmDelete.name}</span>?
              Esta acción no se puede deshacer.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded-lg px-4 py-2 text-sm text-slate-400 transition hover:bg-white/5 hover:text-white"
              >
                Cancelar
              </button>
              <button
                onClick={handleConfirmDelete}
                disabled={actionLoading === confirmDelete.id}
                className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-500 disabled:opacity-50"
              >
                {actionLoading === confirmDelete.id ? "Eliminando..." : "Eliminar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
