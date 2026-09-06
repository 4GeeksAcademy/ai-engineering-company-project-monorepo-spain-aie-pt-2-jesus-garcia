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

const FLOW_STATUSES = ["open", "in_progress", "resolved"];

const FLOW_COLORS: Record<string, string> = {
  open: "bg-amber-500/20 text-amber-300",
  in_progress: "bg-cyan-500/20 text-cyan-300",
  resolved: "bg-emerald-500/20 text-emerald-300",
};

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
    ? `${base} ${FLOW_COLORS[status]} ring-2 ring-white/50 border-white/30`
    : isAllowed
      ? `${base} border-white/10 bg-white/10 text-white cursor-pointer hover:bg-white/20`
      : `${base} border-white/5 bg-slate-800/40 text-slate-600`;

  return (
    <button
      type="button"
      disabled={!isAllowed}
      onClick={() => onSelect(status)}
      className={`${style} ${isSelected && !isCurrent ? "ring-2 ring-white/40" : ""}`}
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

export function StatusFlowModal({ incident, onClose, onTransition }: StatusFlowModalProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!incident) return null;

  const allowed = nextStatuses(incident.status);
  const flowTargets = allowed.filter((s) => s !== "discarded");
  const canDiscard = allowed.includes("discarded");
  const hasTransition = allowed.length > 0;

  function reset() {
    setSelected(null);
    setLoading(false);
    setError(null);
  }

  function handleClose() {
    reset();
    onClose();
  }

  function handleDiscard() {
    setSelected("discarded");
  }

  async function handleConfirm() {
    if (!incident || !selected) return;
    setLoading(true);
    setError(null);
    try {
      await onTransition(incident.id, selected);
      reset();
    } catch {
      setError("Error al cambiar el estado");
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={handleClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-xl border border-white/10 bg-slate-900 shadow-xl"
      >
        <div className="p-6">
          <h2 className="text-xl font-bold text-white">Transición de estado</h2>
          <p className="mt-1 line-clamp-1 text-sm text-slate-400">{incident.title}</p>

          <div className="mt-6 flex flex-col items-center">
            {FLOW_STATUSES.map((status, index) => (
              <div key={status} className="flex flex-col items-center">
                <StatusNode
                  status={status}
                  current={incident.status}
                  allowed={flowTargets}
                  selected={selected}
                  onSelect={setSelected}
                />
                {index < FLOW_STATUSES.length - 1 && <Connector />}
              </div>
            ))}
          </div>

          {!hasTransition && (
            <p className="mt-6 text-center text-sm text-slate-500">
              Esta incidencia está en un estado final y no admite cambios.
            </p>
          )}
          {error && <p className="mt-4 text-center text-sm text-rose-400">{error}</p>}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-white/10 px-6 py-4">
          <button
            type="button"
            onClick={handleDiscard}
            disabled={!canDiscard || loading}
            className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-500 disabled:opacity-40"
          >
            Descartar incidencia
          </button>
          <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleClose}
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
      </div>

      <div onClick={(e) => e.stopPropagation()}>
        <ConfirmDialog
          open={selected !== null}
          title="Cambiar estado"
          danger={selected === "discarded"}
          message={`¿Confirmas cambiar la incidencia "${
            incident.title
          }" a "${selected ? (INCIDENT_STATUSES[selected] ?? selected) : ""}"?`}
          confirmLabel={loading ? "Guardando..." : "Confirmar"}
          loading={loading}
          onConfirm={handleConfirm}
          onCancel={reset}
        />
      </div>
    </div>
  );
}
