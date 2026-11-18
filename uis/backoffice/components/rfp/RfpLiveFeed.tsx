"use client";

import Link from "next/link";
import type { RfpLiveNotification } from "@/hooks/useRfpRealtime";
import { RFP_STATUS_LABELS, SERVICE_LABELS } from "@/lib/rfp-types";
import type { RealtimeStatus } from "@/lib/sse";

interface RfpLiveFeedProps {
  notifications: RfpLiveNotification[];
  status: RealtimeStatus;
  attempt: number;
  nextRetryMs: number | null;
  onDismiss: (ticketId: string) => void;
  onClear: () => void;
}

function connectionLabel(
  status: RealtimeStatus,
  attempt: number,
  nextRetryMs: number | null,
): string {
  switch (status) {
    case "open":
      return "Tiempo real · conectado";
    case "connecting":
      return "Conectando al stream…";
    case "reconnecting": {
      const seconds =
        nextRetryMs !== null ? Math.max(1, Math.round(nextRetryMs / 1000)) : null;
      return seconds
        ? `Reconectando (intento ${attempt} en ${seconds} s)…`
        : `Reconectando (intento ${attempt})…`;
    }
    case "unauthorized":
      return "Sesión sin autorización";
    case "stopped":
      return "Stream detenido";
    default:
      return "Tiempo real inactivo";
  }
}

function connectionStyles(status: RealtimeStatus): string {
  switch (status) {
    case "open":
      return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
    case "connecting":
    case "reconnecting":
      return "bg-amber-500/15 text-amber-300 border-amber-500/30";
    case "unauthorized":
      return "bg-rose-500/15 text-rose-300 border-rose-500/30";
    default:
      return "bg-slate-500/15 text-slate-300 border-slate-500/30";
  }
}

function formatTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

/**
 * Panel de notificaciones en vivo: visualmente distinto del resto del
 * dashboard (borde degradado, pulso y chip "Nuevo"/"Recuperado").
 */
export function RfpLiveFeed({
  notifications,
  status,
  attempt,
  nextRetryMs,
  onDismiss,
  onClear,
}: RfpLiveFeedProps) {
  return (
    <section
      aria-label="Notificaciones de RFPs en tiempo real"
      aria-live="polite"
      className="rounded-xl border border-cyan-400/30 bg-gradient-to-br from-cyan-500/10 via-slate-900/70 to-emerald-500/10 p-5"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            {status === "open" ? (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            ) : null}
            <span
              className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                status === "open" ? "bg-emerald-400" : "bg-slate-500"
              }`}
            />
          </span>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-cyan-200">
            Llegada de RFPs en vivo
          </h2>
          <span className="hidden text-xs text-slate-400 sm:inline">
            evento <code className="text-cyan-300">rfp_ticket_created</code>
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span
            data-testid="realtime-status"
            className={`rounded-full border px-3 py-1 text-xs font-medium ${connectionStyles(status)}`}
          >
            {connectionLabel(status, attempt, nextRetryMs)}
          </span>
          {notifications.length > 0 ? (
            <button
              type="button"
              onClick={onClear}
              className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-slate-300 transition hover:bg-white/5"
            >
              Limpiar
            </button>
          ) : null}
        </div>
      </header>

      {notifications.length === 0 ? (
        <p className="mt-4 text-sm text-slate-400">
          Escuchando el stream. Cuando entre una RFP válida aparecerá aquí sin
          recargar la página.
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {notifications.map((item) => (
            <li
              key={item.ticketId}
              className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-cyan-400/20 bg-slate-950/50 px-4 py-3"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${
                      item.recovered
                        ? "border-amber-400/40 bg-amber-400/15 text-amber-200"
                        : "border-emerald-400/40 bg-emerald-400/15 text-emerald-200"
                    }`}
                  >
                    {item.recovered ? "Recuperado" : "Nuevo"}
                  </span>
                  <Link
                    href={`/rfp/${item.ticketId}`}
                    className="font-semibold text-cyan-300 hover:text-cyan-200"
                  >
                    {item.rfpId}
                  </Link>
                  <span className="text-xs text-slate-400">
                    {RFP_STATUS_LABELS[item.status] ?? item.status}
                  </span>
                </div>
                <p className="mt-1 truncate text-sm text-white">
                  {item.clientName ?? "Cliente por confirmar"}
                  {item.clientCountry ? (
                    <span className="text-slate-400"> · {item.clientCountry}</span>
                  ) : null}
                </p>
                <p className="mt-0.5 text-xs text-slate-400">
                  {item.servicesRequested.length > 0
                    ? item.servicesRequested
                        .map((service) => SERVICE_LABELS[service] ?? service)
                        .join(" · ")
                    : "Metadatos en extracción"}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <time
                  className="text-xs text-slate-500"
                  dateTime={item.receivedAt}
                >
                  {formatTime(item.receivedAt)}
                </time>
                <button
                  type="button"
                  onClick={() => onDismiss(item.ticketId)}
                  aria-label={`Descartar notificación de ${item.rfpId}`}
                  className="rounded-md border border-white/10 px-2 py-0.5 text-sm text-slate-400 transition hover:bg-white/5 hover:text-white"
                >
                  ×
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
