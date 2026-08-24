"use client";

import { useState } from "react";
import type { Incident } from "@/lib/types";
import { INCIDENT_STATUSES, nextStatuses } from "@/lib/types";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface StatusFlowModalProps {
  incident: Incident | null;
  onClose: () => void;
  onTransition: (id: string, target: string) => Promise<void>;
}

function StatusNode({
  status,
  current,
  allowed,
  selected,
  onSelect,
}: {
  status: string;
  current: string;
  allowed: string[];
  selected: string | null;
  onSelect: (s: string) => void;
}) {
  const isCurrent = status === current;
  const isAllowed = allowed.includes(status);
  const isSelected = selected === status;

  const base =
    "rounded-xl border px-5 py-3 text-sm font-medium transition select-none";
  const style = isCurrent
    ? `${base} bg-slate-800 text-white ring-2 ring-white/40 border-white/20`
    : isAllowed
      ? `${base} border-white/10 bg-cyan-600 text-white cursor-pointer hover:bg-cyan-500`
      : `${base} border-white/5 bg-slate-800/40 text-slate-600`;

  return (
    <button
      type="button"
      disabled={!isAllowed}
      onClick={() => onSelect(status)}
      className={`${style} ${isSelected && !isCurrent ? "ring-2 ring-cyan-400" : ""}`}
    >
      {INCIDENT_STATUSES[status] ?? status}
      {(isCurrent || isAllowed) && (
        <span className="ml-2 text-xs opacity-80">
          {isCurrent ? "▲ actual" : "→ destino"}
        </span>
      )}
    </button>
  );
}

function Connector() {
  return (
    <div className="my-1 flex flex-col items-center">
      <div className="h-5 w-px bg-white/20" />
    </div>
  );
}

function BranchConnector() {
  return (
    <div className="mt-1 mb-2 flex w-64 items-center">
      <div className="h-px flex-1 bg-white/20" />
      <div className="h-px flex-1 bg-white/20" />
    </div>
  );
}

export function StatusFlowModal({ incident, onClose, onTransition }: StatusFlowModalProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!incident) return null;

  const allowed = nextStatuses(incident.status);
  const hasTransition = allowed.length > 0;

  async function handleConfirm() {
    if (!incident || !selected) return;
    setLoading(true);
    setError(null);
    try {
      await onTransition(incident.id, selected);
      onClose();
    } catch {
      setError("Error al cambiar el estado");
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-slate-900 shadow-xl">
        <div className="p-6">
          <h2 className="text-xl font-bold text-white">Transición de estado</h2>
          <p className="mt-1 line-clamp-1 text-sm text-slate-400">{incident.title}</p>

          <div className="mt-6 flex flex-col items-center">
            <StatusNode
              status="open"
              current={incident.status}
              allowed={allowed}
              selected={selected}
              onSelect={setSelected}
            />
            <Connector />
            <StatusNode
              status="in_progress"
              current={incident.status}
              allowed={allowed}
              selected={selected}
              onSelect={setSelected}
            />
            <BranchConnector />
            <div className="flex w-full max-w-xs items-center justify-between gap-4">
              <StatusNode
                status="resolved"
                current={incident.status}
                allowed={allowed}
                selected={selected}
                onSelect={setSelected}
              />
              <StatusNode
                status="discarded"
                current={incident.status}
                allowed={allowed}
                selected={selected}
                onSelect={setSelected}
              />
            </div>
          </div>

          {!hasTransition && (
            <p className="mt-6 text-center text-sm text-slate-500">
              Esta incidencia está en un estado final y no admite cambios.
            </p>
          )}
          {error && <p className="mt-4 text-center text-sm text-rose-400">{error}</p>}
        </div>

        <div className="flex justify-end gap-3 border-t border-white/10 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-slate-400 transition hover:bg-white/5 hover:text-white"
          >
            Cerrar
          </button>
          {selected && (
            <button
              type="button"
              onClick={handleConfirm}
              disabled={loading}
              className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:opacity-50"
            >
              {loading ? "Guardando..." : "Aplicar cambio"}
            </button>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={selected !== null}
        title="Cambiar estado"
        message={`¿Confirmas cambiar la incidencia "${
          incident.title
        }" a "${selected ? (INCIDENT_STATUSES[selected] ?? selected) : ""}"?`}
        confirmLabel={loading ? "Guardando..." : "Confirmar"}
        loading={loading}
        onConfirm={handleConfirm}
        onCancel={() => setSelected(null)}
      />
    </div>
  );
}
