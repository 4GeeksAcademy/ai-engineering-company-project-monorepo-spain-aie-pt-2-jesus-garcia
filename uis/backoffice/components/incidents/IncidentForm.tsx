"use client";

import { useState } from "react";
import type { IncidentCreate } from "@/lib/types";
import {
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_BRANCHES,
} from "@/lib/types";
import { friendlyError } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface IncidentFormProps {
  onSubmit: (data: IncidentCreate) => Promise<void>;
  onClose: () => void;
}

export function IncidentForm({ onSubmit, onClose }: IncidentFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [origin, setOrigin] = useState("branch");
  const [branch, setBranch] = useState("central");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pendingSubmit, setPendingSubmit] = useState<IncidentCreate | null>(null);

  function validate(): boolean {
    const newErrors: Record<string, string> = {};
    if (!title.trim()) newErrors.title = "El título es obligatorio";
    if (!description.trim()) newErrors.description = "La descripción es obligatoria";
    if (!origin) newErrors.origin = "El origen es obligatorio";
    if (!branch) newErrors.branch = "La sede es obligatoria";
    if (!category) newErrors.category = "La categoría es obligatoria";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setPendingSubmit({
      title: title.trim(),
      description: description.trim(),
      origin,
      branch,
      category,
      status: "open",
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
          <h2 className="mb-4 text-xl font-bold text-white">Nueva incidencia</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-slate-400">Título *</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-base text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="Describe la incidencia en una frase"
              />
              {errors.title && <p className="mt-1 text-xs text-rose-400">{errors.title}</p>}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm text-slate-400">Origen *</label>
                <select
                  value={origin}
                  onChange={(e) => setOrigin(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-base text-white focus:border-cyan-500 focus:outline-none"
                >
                  {Object.entries(INCIDENT_ORIGINS).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1 block text-sm text-slate-400">Categoría *</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-base text-white focus:border-cyan-500 focus:outline-none"
                >
                  <option value="">Selecciona…</option>
                  {Object.entries(INCIDENT_CATEGORIES).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
                {errors.category && <p className="mt-1 text-xs text-rose-400">{errors.category}</p>}
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-400">Sede *</label>
              <select
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-base text-white focus:border-cyan-500 focus:outline-none"
              >
                {Object.entries(INCIDENT_BRANCHES).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-400">Descripción *</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-base text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                placeholder="Detalle de lo ocurrido"
              />
              {errors.description && (
                <p className="mt-1 text-xs text-rose-400">{errors.description}</p>
              )}
            </div>

            {errors.submit && <p className="text-sm text-rose-400">{errors.submit}</p>}
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
            Crear incidencia
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingSubmit !== null}
        title="Crear incidencia"
        message={`Estás a punto de reportar la incidencia "${
          title.trim() || "sin título"
        }". ¿Confirmas los datos?`}
        confirmLabel="Crear incidencia"
        loading={loading}
        onConfirm={handleConfirm}
        onCancel={() => setPendingSubmit(null)}
      />
    </div>
  );
}
