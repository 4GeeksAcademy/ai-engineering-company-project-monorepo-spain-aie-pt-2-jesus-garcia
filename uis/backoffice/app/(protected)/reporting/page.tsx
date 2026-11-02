"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useAsyncData } from "@/hooks/useAsyncData";
import {
  ApiRequestError,
  fetchLatestPipelineRun,
  fetchWeeklyPerformance,
  friendlyError,
  triggerPipelineRun,
} from "@/lib/api";
import { computeWeeklyTotals, WAREHOUSE_LABELS } from "@/lib/types";
import type { PipelineRunLatest, WeeklyPerformanceReport } from "@/lib/types";
import { MetricCard } from "@/components/ui/MetricCard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

const inputClass =
  "rounded-lg border border-white/10 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none";

function formatRate(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function formatDate(value: string | null): string {
  return value ? value.slice(0, 10) : "—";
}

function statusClass(status: string): string {
  switch (status) {
    case "success":
      return "bg-emerald-500/15 text-emerald-300";
    case "failed":
      return "bg-rose-500/15 text-rose-300";
    case "running":
      return "bg-amber-500/15 text-amber-300";
    default:
      return "bg-slate-500/15 text-slate-300";
  }
}

export default function ReportingPage() {
  const { token } = useAuth();
  const [weekStart, setWeekStart] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  const { data, loading, error, reload } = useAsyncData(
    async () => {
      let report: WeeklyPerformanceReport | null = null;
      try {
        report = await fetchWeeklyPerformance(
          { week_start: weekStart || undefined },
          token,
        );
      } catch (err) {
        if (!(err instanceof ApiRequestError && err.status === 404)) throw err;
      }

      let run: PipelineRunLatest | null = null;
      try {
        run = await fetchLatestPipelineRun(token);
      } catch (err) {
        if (!(err instanceof ApiRequestError && err.status === 404)) throw err;
      }
      return { report, run };
    },
    [weekStart, token],
    friendlyError,
  );

  const totals = useMemo(
    () => (data?.report ? computeWeeklyTotals(data.report.entries) : null),
    [data],
  );

  useEffect(() => {
    if (!polling || data?.run?.status !== "running") return;
    const timer = setInterval(reload, 5000);
    return () => clearInterval(timer);
  }, [polling, data?.run?.status, reload]);

  async function handleTrigger() {
    setTriggering(true);
    setTriggerError(null);
    try {
      await triggerPipelineRun(
        { week_start: weekStart || undefined },
        token,
      );
      setPolling(true);
      reload();
    } catch (err) {
      setTriggerError(friendlyError(err));
    } finally {
      setTriggering(false);
      setConfirmOpen(false);
    }
  }

  const run = data?.run ?? null;
  const report = data?.report ?? null;

  return (
    <>
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-white">Desempeño semanal</h1>
        <p className="mt-2 text-sm text-slate-300">
          Consolidado por almacén y cliente: volumen de entrada, throughput,
          quiebres de stock y precisión de inventario.
        </p>
      </header>

      <section
        aria-label="Controles del reporte"
        className="mb-6 flex flex-wrap items-end gap-4 rounded-xl border border-white/10 bg-white/5 p-5"
      >
        <label className="flex flex-col gap-1 text-sm text-slate-300">
          Semana (lunes)
          <input
            type="date"
            value={weekStart}
            onChange={(event) => setWeekStart(event.target.value)}
            className={inputClass}
            aria-label="Semana del reporte"
          />
        </label>
        <button
          type="button"
          onClick={() => setWeekStart("")}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5"
        >
          Ver la más reciente
        </button>
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={triggering || run?.status === "running"}
          className="ml-auto rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:opacity-50"
        >
          {run?.status === "running" ? "Corrida en curso…" : "Ejecutar ahora"}
        </button>
      </section>

      {triggerError && (
        <p role="alert" className="mb-4 rounded-lg bg-rose-500/10 p-3 text-sm text-rose-300">
          {triggerError}
        </p>
      )}

      <section aria-label="Estado del pipeline" className="mb-6">
        <h2 className="mb-3 text-lg font-semibold text-white">Estado del pipeline</h2>
        {run ? (
          <div className="rounded-xl border border-white/10 bg-white/5 p-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusClass(run.status)}`}>
                {run.status}
              </span>
              <span className="text-sm text-slate-300">
                Semana {formatDate(run.week_start)}
              </span>
              {run.quality_status && (
                <span className="text-sm text-slate-400">
                  Calidad: {run.quality_status}
                </span>
              )}
              {run.stale && (
                <span className="rounded-full bg-amber-500/15 px-3 py-1 text-xs font-semibold text-amber-300">
                  stale
                </span>
              )}
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-300 sm:grid-cols-4">
              <div>
                <dt className="text-slate-400">Extraídas</dt>
                <dd className="font-semibold text-white">{run.rows_extracted}</dd>
              </div>
              <div>
                <dt className="text-slate-400">Rechazadas</dt>
                <dd className="font-semibold text-white">{run.rows_rejected}</dd>
              </div>
              <div>
                <dt className="text-slate-400">Escritas</dt>
                <dd className="font-semibold text-white">{run.rows_written}</dd>
              </div>
              <div>
                <dt className="text-slate-400">Inicio</dt>
                <dd className="font-semibold text-white">
                  {run.started_at ? run.started_at.slice(0, 19).replace("T", " ") : "—"}
                </dd>
              </div>
            </dl>
            {run.error_message && (
              <p className="mt-3 rounded-lg bg-rose-500/10 p-3 text-sm text-rose-300">
                {run.error_message}
              </p>
            )}
          </div>
        ) : (
          <p className="rounded-xl border border-white/10 bg-white/5 p-5 text-sm text-slate-400">
            Aún no hay corridas registradas.
          </p>
        )}
      </section>

      {loading && !data && (
        <p className="text-sm text-slate-300">Cargando reporte…</p>
      )}

      {error && (
        <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-5">
          <p className="text-sm text-rose-300">{error}</p>
          <button
            type="button"
            onClick={reload}
            className="mt-3 rounded-lg bg-rose-600 px-4 py-2 text-sm text-white hover:bg-rose-500"
          >
            Reintentar
          </button>
        </div>
      )}

      {!loading && !error && !report && (
        <p className="rounded-xl border border-white/10 bg-white/5 p-5 text-sm text-slate-400">
          Aún no hay semanas calculadas. Ejecuta el pipeline para generar el
          primer reporte.
        </p>
      )}

      {report && totals && (
        <>
          <section aria-label="Resumen semanal" className="mb-6">
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <h2 className="text-lg font-semibold text-white">
                Semana {formatDate(report.week_start)}
              </h2>
              {report.frozen && (
                <span className="rounded-full bg-cyan-500/15 px-3 py-1 text-xs font-semibold text-cyan-300">
                  congelada
                </span>
              )}
              {report.stale && (
                <span className="rounded-full bg-amber-500/15 px-3 py-1 text-xs font-semibold text-amber-300">
                  stale
                </span>
              )}
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard title="Volumen de entrada" value={totals.inboundUnits} subtitle="unidades" />
              <MetricCard title="Throughput de salida" value={totals.outboundOrders} subtitle="pedidos" />
              <MetricCard title="Quiebres de stock" value={totals.stockoutEvents} subtitle="eventos" />
              <MetricCard
                title="Tasa de discrepancia"
                value={formatRate(totals.discrepancyRate)}
                subtitle={`${totals.discrepancyEvents} discrepancias`}
              />
            </div>
          </section>

          <section aria-label="Detalle por almacén y cliente">
            <h2 className="mb-3 text-lg font-semibold text-white">
              Detalle por almacén y cliente
            </h2>
            <div className="scroll-mt-6 overflow-x-auto rounded-xl border border-white/10 bg-slate-900/60">
              <table className="w-full text-left text-sm">
                <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Almacén</th>
                    <th className="px-4 py-3">Cliente</th>
                    <th className="px-4 py-3 text-right">Entrada</th>
                    <th className="px-4 py-3 text-right">Salida</th>
                    <th className="px-4 py-3 text-right">Quiebres</th>
                    <th className="px-4 py-3 text-right">Discrepancias</th>
                    <th className="px-4 py-3 text-right">Tasa</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 text-slate-200">
                  {report.entries.map((entry) => (
                    <tr key={`${entry.warehouse}-${entry.client_id}`}>
                      <td className="px-4 py-3">
                        {WAREHOUSE_LABELS[entry.warehouse] ?? entry.warehouse}
                      </td>
                      <td className="px-4 py-3">{entry.client_id}</td>
                      <td className="px-4 py-3 text-right">{entry.inbound_units_count}</td>
                      <td className="px-4 py-3 text-right">{entry.outbound_orders_count}</td>
                      <td className="px-4 py-3 text-right">{entry.stockout_events_count}</td>
                      <td className="px-4 py-3 text-right">{entry.discrepancy_events_count}</td>
                      <td className="px-4 py-3 text-right">{formatRate(entry.discrepancy_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="Ejecutar pipeline"
        message={
          weekStart
            ? `Se recalculará la semana ${weekStart}.`
            : "Se recalculará la última semana cerrada y el lookback configurado."
        }
        confirmLabel="Ejecutar"
        loading={triggering}
        onConfirm={handleTrigger}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
