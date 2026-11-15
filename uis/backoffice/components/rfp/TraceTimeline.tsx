"use client";

import { useMemo } from "react";
import {
  DEPARTMENT_LABELS,
  type RfpTrace,
  type RfpTraceEvent,
} from "@/lib/rfp-types";

function formatTime(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(parsed);
}

function EventRow({ event }: { event: RfpTraceEvent }) {
  return (
    <li className="rounded-lg border border-white/10 bg-slate-950/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-white/10 px-2 py-0.5 font-mono text-[11px] text-slate-400">
            #{event.sequence}
          </span>
          <span className="font-semibold text-cyan-200">{event.node}</span>
          <span className="text-slate-300">{event.agent ?? "—"}</span>
          {event.department_id && (
            <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-slate-300">
              {DEPARTMENT_LABELS[event.department_id] ?? event.department_id}
            </span>
          )}
        </div>
        <span className="text-slate-500">
          {formatTime(event.timestamp)}
          {event.duration_ms != null ? ` · ${event.duration_ms} ms` : ""}
        </span>
      </div>
      <details className="mt-2">
        <summary className="cursor-pointer text-[11px] uppercase tracking-wide text-slate-400">
          Input / output
        </summary>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <pre className="max-h-48 overflow-auto rounded-lg bg-black/30 p-2 text-[11px] text-slate-300">
            {JSON.stringify(event.input, null, 2)}
          </pre>
          <pre className="max-h-48 overflow-auto rounded-lg bg-black/30 p-2 text-[11px] text-slate-300">
            {JSON.stringify(event.output, null, 2)}
          </pre>
        </div>
      </details>
    </li>
  );
}

export function TraceTimeline({ trace }: { trace: RfpTrace | null }) {
  const grouped = useMemo(() => {
    const events = trace?.events ?? [];
    const byPart = new Map<number, RfpTraceEvent[]>();
    for (const event of events) {
      const bucket = byPart.get(event.part) ?? [];
      bucket.push(event);
      byPart.set(event.part, bucket);
    }
    return [...byPart.entries()].sort(([a], [b]) => a - b);
  }, [trace]);

  if (!trace || trace.events.length === 0) {
    return null;
  }

  return (
    <section className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Trazabilidad de la ejecución
        </h2>
        <span className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-400">
          {trace.events.length} eventos · {trace.arbitrations.length} arbitrajes
        </span>
      </div>

      {trace.arbitrations.length > 0 && (
        <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-rose-200">
            Arbitrajes
          </p>
          <ul className="mt-2 space-y-2 text-xs text-rose-100">
            {trace.arbitrations.map((arbitration, index) => (
              <li key={`${arbitration.trigger_id}-${arbitration.round}-${index}`}>
                <span className="font-semibold">{arbitration.trigger_id}</span> ·{" "}
                {arbitration.arbitrator ?? "—"} ·{" "}
                {arbitration.resolved ? "resuelto" : "no resuelto"} ·{" "}
                {arbitration.affected_sections.join(", ")}
                {arbitration.rule && (
                  <p className="mt-1 text-rose-200/80">{arbitration.rule}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 space-y-4">
        {grouped.map(([part, events]) => (
          <div key={part}>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Parte {part} · {events.length} eventos
            </h3>
            <ul className="mt-2 space-y-2">
              {events.map((event) => (
                <EventRow key={event.event_id} event={event} />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
