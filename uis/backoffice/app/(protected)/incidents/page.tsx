"use client";

import { useEffect, useState } from "react";
import {
  fetchIncidents,
  fetchIncidentSummary,
  createIncident,
  updateIncidentStatus,
} from "@/lib/api";
import type { Incident, IncidentCreate } from "@/lib/types";
import {
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_BRANCHES,
  INCIDENT_STATUSES,
  INCIDENT_STATUS_ORDER,
  nextStatuses,
} from "@/lib/types";
import { IncidentForm } from "@/components/incidents/IncidentForm";
import { StatusFlowModal } from "@/components/incidents/StatusFlowModal";
import { useAuth } from "@/contexts/AuthContext";

const STATUS_BADGE: Record<string, string> = {
  open: "bg-amber-500/20 text-amber-300",
  in_progress: "bg-cyan-500/20 text-cyan-300",
  resolved: "bg-emerald-500/20 text-emerald-300",
  discarded: "bg-slate-500/20 text-slate-400",
};

export default function IncidentsPage() {
  const { token } = useAuth();

  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [summary, setSummary] = useState<Record<string, number> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState("");
  const [originFilter, setOriginFilter] = useState("");
  const [branchFilter, setBranchFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [flowTarget, setFlowTarget] = useState<Incident | null>(null);

  async function refresh() {
    const fresh = await fetchIncidents(
      {
        status: statusFilter || undefined,
        origin: originFilter || undefined,
        branch: branchFilter || undefined,
        category: categoryFilter || undefined,
      },
      token,
    );
    setIncidents(fresh);
    const s = await fetchIncidentSummary(token);
    setSummary(s.by_status);
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const fresh = await fetchIncidents(
          {
            status: statusFilter || undefined,
            origin: originFilter || undefined,
            branch: branchFilter || undefined,
            category: categoryFilter || undefined,
          },
          token,
        );
        const s = await fetchIncidentSummary(token);
        if (cancelled) return;
        setIncidents(fresh);
        setSummary(s.by_status);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Error al cargar incidencias");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [statusFilter, originFilter, branchFilter, categoryFilter, token]);

  async function handleCreate(data: IncidentCreate) {
    await createIncident(data, token);
    await refresh();
  }

  async function handleTransition(target: string) {
    const incident = flowTarget;
    if (!incident) return;
    if (!nextStatuses(incident.status).includes(target)) {
      setError(`Destino de estado inválido: ${target}`);
      return;
    }
    try {
      await updateIncidentStatus(incident.id, { status: target }, token);
      setFlowTarget(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cambiar el estado");
    }
  }

  const selectClass =
    "rounded-lg border border-white/10 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none";

  return (
    <>
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Gestor de incidencias</h1>
          <p className="mt-2 text-slate-400">
            Registro centralizado de incidencias operativas en USA y España.
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500"
        >
          + Nueva incidencia
        </button>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {INCIDENT_STATUS_ORDER.map((status) => (
          <div
            key={status}
            className="rounded-xl border border-white/10 bg-slate-900/60 p-4"
          >
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {INCIDENT_STATUSES[status]}
            </p>
            <p className="mt-1 text-2xl font-bold text-white">
              {summary?.[status] ?? 0}
            </p>
          </div>
        ))}
      </div>

      <div className="mb-6 flex flex-wrap gap-4">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={selectClass}>
          <option value="">Todos los estados</option>
          {INCIDENT_STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {INCIDENT_STATUSES[s]}
            </option>
          ))}
        </select>
        <select value={originFilter} onChange={(e) => setOriginFilter(e.target.value)} className={selectClass}>
          <option value="">Todos los orígenes</option>
          {Object.entries(INCIDENT_ORIGINS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <select value={branchFilter} onChange={(e) => setBranchFilter(e.target.value)} className={selectClass}>
          <option value="">Todas las sedes</option>
          {Object.entries(INCIDENT_BRANCHES).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className={selectClass}>
          <option value="">Todas las categorías</option>
          {Object.entries(INCIDENT_CATEGORIES).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-rose-400/20 bg-rose-500/10 p-5">
          <p className="text-sm font-medium text-rose-300">Error: {error}</p>
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
                <th className="px-4 py-3 font-medium text-slate-300">Incidencia</th>
                <th className="px-4 py-3 font-medium text-slate-300">Categoría</th>
                <th className="px-4 py-3 font-medium text-slate-300">Sede</th>
                <th className="px-4 py-3 font-medium text-slate-300">Origen</th>
                <th className="px-4 py-3 font-medium text-slate-300">Estado</th>
                <th className="px-4 py-3 font-medium text-slate-300">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {incidents.map((incident) => (
                <tr key={incident.id} className="transition hover:bg-white/5">
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{incident.title}</div>
                    <div className="line-clamp-1 max-w-xs text-xs text-slate-500">
                      {incident.description}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {INCIDENT_CATEGORIES[incident.category] ?? incident.category}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {INCIDENT_BRANCHES[incident.branch] ?? incident.branch}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {INCIDENT_ORIGINS[incident.origin] ?? incident.origin}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                        STATUS_BADGE[incident.status] ?? ""
                      }`}
                    >
                      {INCIDENT_STATUSES[incident.status] ?? incident.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {nextStatuses(incident.status).length > 0 ? (
                        <button
                          onClick={() => setFlowTarget(incident)}
                          className="rounded-lg bg-cyan-600/20 px-3 py-1 text-xs font-medium text-cyan-300 transition hover:bg-cyan-600/40"
                        >
                          Cambiar estado
                        </button>
                      ) : (
                        <span className="text-xs text-slate-600">—</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {incidents.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                    No se encontraron incidencias
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {!loading && incidents.length > 0 && (
        <p className="mt-4 text-sm text-slate-500">
          {incidents.length} incidencia{incidents.length !== 1 ? "s" : ""}
        </p>
      )}

      {showForm && <IncidentForm onSubmit={handleCreate} onClose={() => setShowForm(false)} />}

      <StatusFlowModal
        incident={flowTarget}
        onClose={() => setFlowTarget(null)}
        onTransition={handleTransition}
      />
    </>
  );
}
