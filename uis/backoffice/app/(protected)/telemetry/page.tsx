"use client";

import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { fetchTelemetryReport, friendlyError } from "@/lib/api";
import { computeTelemetrySummary } from "@/lib/types";
import type { TelemetryReport } from "@/lib/types";
import { useAsyncData } from "@/hooks/useAsyncData";
import { usePagination } from "@/hooks/usePagination";
import { MetricCard } from "@/components/ui/MetricCard";
import { Pagination } from "@/components/ui/Pagination";

const inputClass =
  "rounded-lg border border-white/10 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none";

function toDateInput(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function defaultRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - 6);
  return { start: toDateInput(start), end: toDateInput(end) };
}

function startOfDayISO(value: string): string | undefined {
  return value ? `${value}T00:00:00Z` : undefined;
}

function endExclusiveISO(value: string): string | undefined {
  if (!value) return undefined;
  const end = new Date(`${value}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 1);
  return end.toISOString();
}

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function formatMillis(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} ms`;
}

function isEmptyReport(report: TelemetryReport): boolean {
  return Object.values(report.metrics).every((rows) => rows.length === 0);
}

function PagedSection<T>({
  title,
  label,
  rows,
  resetKey,
  children,
}: {
  title: string;
  label: string;
  rows: readonly T[];
  resetKey?: string;
  children: (visibleRows: readonly T[]) => ReactNode;
}) {
  const pagination = usePagination(rows, { resetKey });
  const tableRef = useRef<HTMLDivElement>(null);

  return (
    <section aria-label={title} className="mt-8">
      <h2 className="mb-3 text-lg font-semibold text-white">{title}</h2>
      <div
        ref={tableRef}
        className="scroll-mt-6 overflow-x-auto rounded-xl border border-white/10 bg-slate-900/60"
      >
        <table className="w-full text-left text-sm">{children(pagination.pageItems)}</table>
      </div>
      {rows.length > 0 && (
        <Pagination
          page={pagination.page}
          pageSize={pagination.pageSize}
          total={pagination.total}
          onPageChange={pagination.setPage}
          onPageSizeChange={pagination.setPageSize}
          scrollTargetRef={tableRef}
          label={label}
        />
      )}
    </section>
  );
}

function Bar({ value, max }: { value: number; max: number }) {
  const width = max > 0 ? Math.max(4, (value / max) * 100) : 0;
  return (
    <div className="h-2 w-28 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
      <div className="h-full rounded-full bg-cyan-500" style={{ width: `${width}%` }} />
    </div>
  );
}

export default function TelemetryPage() {
  const initial = useMemo(() => defaultRange(), []);
  const [startDate, setStartDate] = useState(initial.start);
  const [endDate, setEndDate] = useState(initial.end);
  const rangeKey = `${startDate}|${endDate}`;

  const { data, loading, error, reload } = useAsyncData(
    () =>
      fetchTelemetryReport({
        start_date: startOfDayISO(startDate),
        end_date: endExclusiveISO(endDate),
      }),
    [startDate, endDate],
    friendlyError,
  );

  const summary = useMemo(
    () => (data ? computeTelemetrySummary(data.metrics) : null),
    [data],
  );

  const maxEventCount = useMemo(
    () =>
      Math.max(
        1,
        ...(data?.metrics.events_per_day.map((row) => row.event_count) ?? []),
      ),
    [data],
  );

  const maxErrorCount = useMemo(
    () =>
      Math.max(
        1,
        ...(data?.metrics.errors_by_type.map((row) => row.error_count) ?? []),
      ),
    [data],
  );

  return (
    <>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Telemetría</h1>
        <p className="mt-2 text-slate-400">
          Métricas operativas de volumen, errores, latencia y autenticación.
        </p>
      </div>

      <div className="mb-6 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-sm text-slate-300">
          Desde
          <input
            type="date"
            aria-label="Desde"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            className={inputClass}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-300">
          Hasta
          <input
            type="date"
            aria-label="Hasta"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            className={inputClass}
          />
        </label>
        <button
          onClick={reload}
          className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-600"
        >
          Actualizar
        </button>
      </div>

      {data && (
        <p className="mb-6 text-sm text-slate-400">
          Periodo:{" "}
          <time dateTime={data.period.from}>{data.period.from}</time>
          {" → "}
          <time dateTime={data.period.to}>{data.period.to}</time>
        </p>
      )}

      {error && (
        <div className="mb-6 rounded-xl border border-rose-400/20 bg-rose-500/10 p-5">
          <p className="text-sm font-medium text-rose-300">Error: {error}</p>
          <button
            onClick={reload}
            className="mt-3 rounded-lg bg-rose-500/20 px-4 py-2 text-sm font-medium text-rose-200 transition hover:bg-rose-500/30"
          >
            Reintentar
          </button>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
        </div>
      )}

      {!loading && data && summary && (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard title="Eventos totales" value={summary.totalEvents} />
            <MetricCard
              title="Tasa de error"
              value={formatPercent(summary.errorRate)}
              subtitle="Fallos sobre eventos totales"
            />
            <MetricCard
              title="Latencia media"
              value={formatMillis(summary.avgLatency)}
              subtitle="api_response_time"
            />
            <MetricCard
              title="Fallos de login"
              value={formatPercent(summary.authFailureRate)}
              subtitle="Sobre intentos de autenticación"
            />
          </div>

          {isEmptyReport(data) ? (
            <div className="rounded-xl border border-white/10 bg-slate-900/60 p-8 text-center text-slate-300">
              No hay eventos en el periodo seleccionado.
            </div>
          ) : (
            <>
              <PagedSection
                title="Eventos por día"
                label="eventos"
                rows={data.metrics.events_per_day}
                resetKey={rangeKey}
              >
                {(visibleRows) => (
                  <>
                    <thead className="border-b border-white/10 bg-slate-800/50">
                      <tr>
                        <th className="px-4 py-3 font-medium text-slate-300">Fecha</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Tipo</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Eventos</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Volumen</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {visibleRows.map((row) => (
                        <tr key={`${row.date}-${row.event_type}`}>
                          <td className="px-4 py-3 text-slate-300">{row.date}</td>
                          <td className="px-4 py-3 font-medium text-white">{row.event_type}</td>
                          <td className="px-4 py-3 text-slate-200">{row.event_count}</td>
                          <td className="px-4 py-3">
                            <Bar value={row.event_count} max={maxEventCount} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </>
                )}
              </PagedSection>

              <PagedSection
                title="Tasa de error por día"
                label="días"
                rows={data.metrics.error_rate_by_day}
                resetKey={rangeKey}
              >
                {(visibleRows) => (
                  <>
                    <thead className="border-b border-white/10 bg-slate-800/50">
                      <tr>
                        <th className="px-4 py-3 font-medium text-slate-300">Fecha</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Eventos</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Errores</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Tasa</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {visibleRows.map((row) => (
                        <tr key={row.date}>
                          <td className="px-4 py-3 text-slate-300">{row.date}</td>
                          <td className="px-4 py-3 text-slate-200">{row.event_count}</td>
                          <td className="px-4 py-3 text-slate-200">{row.error_count}</td>
                          <td className="px-4 py-3">
                            <span className="inline-block rounded-full bg-rose-500/20 px-2 py-0.5 text-xs font-medium text-rose-300">
                              {formatPercent(row.error_rate)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </>
                )}
              </PagedSection>

              <PagedSection
                title="Errores por tipo"
                label="errores"
                rows={data.metrics.errors_by_type}
                resetKey={rangeKey}
              >
                {(visibleRows) => (
                  <>
                    <thead className="border-b border-white/10 bg-slate-800/50">
                      <tr>
                        <th className="px-4 py-3 font-medium text-slate-300">Fecha</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Tipo</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Errores</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Concentración</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {visibleRows.map((row) => (
                        <tr key={`${row.date}-${row.event_type}`}>
                          <td className="px-4 py-3 text-slate-300">{row.date}</td>
                          <td className="px-4 py-3 font-medium text-white">{row.event_type}</td>
                          <td className="px-4 py-3 text-slate-200">{row.error_count}</td>
                          <td className="px-4 py-3">
                            <Bar value={row.error_count} max={maxErrorCount} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </>
                )}
              </PagedSection>

              <PagedSection
                title="Latencia por día"
                label="días"
                rows={data.metrics.latency_per_day}
                resetKey={rangeKey}
              >
                {(visibleRows) => (
                  <>
                    <thead className="border-b border-white/10 bg-slate-800/50">
                      <tr>
                        <th className="px-4 py-3 font-medium text-slate-300">Fecha</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Media</th>
                        <th className="px-4 py-3 font-medium text-slate-300">p50</th>
                        <th className="px-4 py-3 font-medium text-slate-300">p95</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Muestras</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {visibleRows.map((row) => (
                        <tr key={row.date}>
                          <td className="px-4 py-3 text-slate-300">{row.date}</td>
                          <td className="px-4 py-3 text-slate-200">{formatMillis(row.avg_ms)}</td>
                          <td className="px-4 py-3 text-slate-200">{formatMillis(row.p50_ms)}</td>
                          <td className="px-4 py-3 text-slate-200">{formatMillis(row.p95_ms)}</td>
                          <td className="px-4 py-3 text-slate-200">{row.sample_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </>
                )}
              </PagedSection>

              <PagedSection
                title="Fallos de autenticación"
                label="días"
                rows={data.metrics.auth_failure_rate}
                resetKey={rangeKey}
              >
                {(visibleRows) => (
                  <>
                    <thead className="border-b border-white/10 bg-slate-800/50">
                      <tr>
                        <th className="px-4 py-3 font-medium text-slate-300">Fecha</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Fallidos</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Correctos</th>
                        <th className="px-4 py-3 font-medium text-slate-300">Tasa</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {visibleRows.map((row) => (
                        <tr key={row.date}>
                          <td className="px-4 py-3 text-slate-300">{row.date}</td>
                          <td className="px-4 py-3 text-slate-200">{row.failed}</td>
                          <td className="px-4 py-3 text-slate-200">{row.succeeded}</td>
                          <td className="px-4 py-3">
                            <span className="inline-block rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
                              {formatPercent(row.failure_rate)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </>
                )}
              </PagedSection>
            </>
          )}
        </>
      )}
    </>
  );
}
