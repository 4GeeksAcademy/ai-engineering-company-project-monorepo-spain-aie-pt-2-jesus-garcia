"use client";

import type { SlaStatus } from "@/lib/types";
import type { SlaThresholdAlertPayload } from "@/lib/realtime-types";

interface SlaAlertBannerProps {
  status: SlaStatus | null;
  liveAlert: SlaThresholdAlertPayload | null;
  live: boolean;
  loading: boolean;
  error: string | null;
  evaluating: boolean;
  evaluateError: string | null;
  onEvaluate: () => void;
}

const COUNTRY_LABELS: Record<string, string> = {
  US: "Estados Unidos · Los Ángeles",
  Spain: "España · Zaragoza",
};

function formatPct(value: number | null): string {
  return value === null ? "sin datos" : `${value.toFixed(1)}%`;
}

/**
 * Alerta de umbral de negocio: SLA de entrega a tiempo < 90 % por país.
 * Regla del briefing (aviso a Thomas y Ana). Se alimenta del snapshot REST y
 * se actualiza en vivo con el evento `sla_threshold_alert`.
 */
export function SlaAlertBanner({
  status,
  liveAlert,
  live,
  loading,
  error,
  evaluating,
  evaluateError,
  onEvaluate,
}: SlaAlertBannerProps) {
  const breached = (status?.countries ?? []).filter((item) => item.breached);

  return (
    <section
      aria-label="Alerta de umbral de SLA de entrega"
      className={`mb-6 rounded-xl border p-5 ${
        breached.length > 0
          ? "border-rose-500/40 bg-rose-500/10"
          : "border-white/10 bg-white/5"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2
            className={`text-sm font-semibold uppercase tracking-wide ${
              breached.length > 0 ? "text-rose-200" : "text-slate-300"
            }`}
          >
            Umbral de negocio · SLA de entrega
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Regla del briefing: por debajo del{" "}
            <span className="font-semibold text-slate-200">
              {status?.threshold_pct ?? 90}%
            </span>{" "}
            en cualquiera de los dos países se avisa a Thomas Harry (CEO) y Ana
            Whitfield (Warehouse Operations).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              live
                ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300"
                : "border-slate-500/30 bg-slate-500/15 text-slate-300"
            }`}
          >
            {live ? "Alerta en vivo" : "Stream inactivo"}
          </span>
          <button
            type="button"
            onClick={onEvaluate}
            disabled={evaluating}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-sm text-slate-200 transition hover:bg-white/5 disabled:opacity-50"
          >
            {evaluating ? "Evaluando…" : "Evaluar umbral SLA"}
          </button>
        </div>
      </div>

      {evaluateError ? (
        <p role="alert" className="mt-3 text-sm text-rose-300">
          {evaluateError}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-3 text-sm text-rose-300">
          {error}
        </p>
      ) : null}

      {loading && !status ? (
        <p className="mt-4 text-sm text-slate-400">Cargando SLA…</p>
      ) : breached.length > 0 ? (
        <div className="mt-4 space-y-2">
          {breached.map((item) => (
            <div
              key={item.country}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-500/30 bg-slate-950/40 px-4 py-3"
            >
              <div>
                <p className="text-sm font-semibold text-white">
                  {COUNTRY_LABELS[item.country] ?? item.country}
                </p>
                <p className="text-xs text-slate-300">
                  {formatPct(item.on_time_pct)} de entregas a tiempo · umbral{" "}
                  {status?.threshold_pct ?? 90}%
                </p>
              </div>
              <p className="text-xs text-rose-200">
                Avisar a{" "}
                {item.recipients.length > 0
                  ? item.recipients
                      .map((recipient) => recipient.name)
                      .join(" y ")
                  : "Thomas Harry y Ana Whitfield"}
              </p>
            </div>
          ))}
          {liveAlert ? (
            <p className="text-xs text-rose-300">
              Nuevo cruce de umbral recibido: {liveAlert.country} ·{" "}
              {formatPct(liveAlert.on_time_pct)}
            </p>
          ) : null}
        </div>
      ) : status ? (
        <p className="mt-4 text-sm text-emerald-300">
          SLA dentro del objetivo en ambos países (semana {status.week_start}).
        </p>
      ) : (
        <p className="mt-4 text-sm text-slate-400">
          No hay datos de SLA publicados todavía.
        </p>
      )}
    </section>
  );
}
