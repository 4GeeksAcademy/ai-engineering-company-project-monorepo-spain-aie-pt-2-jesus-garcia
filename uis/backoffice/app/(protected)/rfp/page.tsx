"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchRfpTickets, friendlyError } from "@/lib/api";
import {
  RFP_STATUS_LABELS,
  formatRfpDate,
  type RfpStatus,
} from "@/lib/rfp-types";
import { useAsyncData } from "@/hooks/useAsyncData";
import { useAuth } from "@/contexts/AuthContext";
import { RfpStatusBadge } from "@/components/rfp/RfpStatusBadge";
import { RfpUploader } from "@/components/rfp/RfpUploader";

const FILTERS: Array<{ value: "" | RfpStatus; label: string }> = [
  { value: "", label: "Todos" },
  { value: "analizando", label: "Analizando" },
  { value: "analisis_completo", label: "Análisis completo" },
  { value: "generando_borrador", label: "Generando borrador" },
  { value: "en_evaluación", label: "En evaluación" },
  { value: "needs_human_review", label: "Revisión humana" },
  { value: "esperando_aprobación", label: "Esperando aprobación" },
  { value: "descartado", label: "Descartado" },
  { value: "error", label: "Error" },
];

const COUNT_STATUSES: RfpStatus[] = [
  "analizando",
  "analisis_completo",
  "generando_borrador",
  "en_evaluación",
  "needs_human_review",
  "esperando_aprobación",
  "descartado",
  "error",
];

export default function RfpPage() {
  const { token, user } = useAuth();
  const isManager = user?.role === "admin" || user?.role === "manager";
  const [filter, setFilter] = useState<"" | RfpStatus>("");

  const { data, loading, error, reload } = useAsyncData(
    () =>
      isManager
        ? fetchRfpTickets(token, filter ? { status: filter } : undefined)
        : Promise.resolve([]),
    [token, filter, isManager],
    friendlyError,
  );

  const pending = useMemo(
    () =>
      (data ?? []).some((ticket) =>
        ["analizando", "generando_borrador", "en_evaluación"].includes(
          ticket.status,
        ),
      ),
    [data],
  );

  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(reload, 3000);
    return () => window.clearInterval(timer);
  }, [pending, reload]);

  const counts = useMemo(() => {
    const base: Record<string, number> = {};
    for (const ticket of data ?? []) {
      base[ticket.status] = (base[ticket.status] ?? 0) + 1;
    }
    return base;
  }, [data]);

  if (!isManager) {
    return (
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 text-sm text-amber-200">
        Solo un administrador o manager puede recibir y consultar RFPs.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Recepción de RFPs</h1>
        <p className="mt-1 text-sm text-slate-300">
          Sube las solicitudes de propuesta en PDF. Cada archivo crea un ticket
          que pasa de <span className="text-cyan-300">analizando</span> a{" "}
          <span className="text-emerald-300">análisis completo</span> o{" "}
          <span className="text-slate-300">descartado</span>.
        </p>
      </header>

      <RfpUploader onUploaded={reload} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {COUNT_STATUSES.map((status) => (
          <div
            key={status}
            className="rounded-xl border border-white/10 bg-slate-900/60 p-4"
          >
            <p className="text-xs uppercase tracking-wide text-slate-400">
              {RFP_STATUS_LABELS[status]}
            </p>
            <p className="mt-1 text-2xl font-bold text-white">
              {counts[status] ?? 0}
            </p>
          </div>
        ))}
      </div>

      <section className="rounded-xl border border-white/10 bg-slate-900/60">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            Tickets
          </h2>
          <label className="flex items-center gap-2 text-xs text-slate-400">
            Estado
            <select
              value={filter}
              onChange={(event) => setFilter(event.target.value as "" | RfpStatus)}
              className="rounded-md border border-white/15 bg-slate-950 px-3 py-1.5 text-sm text-white"
              aria-label="Filtrar tickets por estado"
            >
              {FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {loading && !data ? (
          <p className="px-5 py-8 text-sm text-slate-400">Cargando tickets…</p>
        ) : error ? (
          <p className="px-5 py-8 text-sm text-rose-300">{error}</p>
        ) : (data ?? []).length === 0 ? (
          <p className="px-5 py-8 text-sm text-slate-400">
            Todavía no hay RFPs recibidas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-400">
                <tr className="border-b border-white/10">
                  <th className="px-5 py-3">RFP</th>
                  <th className="px-5 py-3">Cliente</th>
                  <th className="px-5 py-3">País / moneda</th>
                  <th className="px-5 py-3">Estado</th>
                  <th className="px-5 py-3">Etapa</th>
                  <th className="px-5 py-3">Actualizado</th>
                </tr>
              </thead>
              <tbody>
                {(data ?? []).map((ticket) => (
                  <tr
                    key={ticket.ticket_id}
                    className="border-b border-white/5 last:border-0 hover:bg-white/5"
                  >
                    <td className="px-5 py-3">
                      <Link
                        href={`/rfp/${ticket.ticket_id}`}
                        className="font-semibold text-cyan-300 hover:text-cyan-200"
                      >
                        {ticket.rfp_id}
                      </Link>
                      <p className="text-xs text-slate-400">
                        {ticket.original_filename}
                      </p>
                    </td>
                    <td className="px-5 py-3 text-slate-200">
                      {ticket.client_name ?? "—"}
                    </td>
                    <td className="px-5 py-3 text-slate-300">
                      {ticket.client_country ?? "—"}
                      {ticket.currency ? ` · ${ticket.currency}` : ""}
                    </td>
                    <td className="px-5 py-3">
                      <RfpStatusBadge status={ticket.status} />
                      {ticket.status === "descartado" && ticket.discard_reason ? (
                        <p className="mt-1 max-w-xs text-xs text-slate-400">
                          {ticket.discard_reason}
                        </p>
                      ) : null}
                      {ticket.status === "error" && ticket.error_message ? (
                        <p className="mt-1 max-w-xs text-xs text-rose-300">
                          {ticket.error_message}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-400">
                      {ticket.pipeline_stage ?? "—"}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-400">
                      {formatRfpDate(ticket.updated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
